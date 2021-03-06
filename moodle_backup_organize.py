#Organize stuff downloaded from a Moodle backup file
#Be sure to extract the backup's contents into a directory first
#(Rename it to .ZIP and extract into a directory)

#Some of this code is based on code found at
#http://www.reades.com/2012/11/29/mb-archives/

import xml.etree.ElementTree as etree
import shutil
import os
import sys
import re
import html
import urllib

#One dependency
#Can run without, but risk of errors
try:
    import pathvalidate
    HAS_PATHVALIDATE = True
except ImportError:
    print("Warning: Running without pathvalidate. May result in failures "
        "due to invalid file names. To ensure this does not happen, do"
        "pip install pathvalidate.")
    HAS_PATHVALIDATE = False

FILES_XML = 'files.xml'
CONTENT_XML = 'moodle_backup.xml'
QUESTIONS_XML = 'questions.xml'

INDEX_FILENAME = 'index.html'

NEW_FILES_DIR = 'content'
NEW_HTML_DIR = 'html'
OLD_FILES_DIR = 'files'

ASSIGNMENT = 'assign'
PAGE = 'page'
URL = 'url'
RESOURCE = 'resource'
FOLDER = 'folder'
QUIZ = 'quiz'

ACTIVITY_NAMES = {ASSIGNMENT : 'Assignments', PAGE : 'Pages', URL : 'URLs',\
    RESOURCE : 'Resources', FOLDER : 'Folders', QUIZ : 'Quizzes'}

MOODLE_PLUGIN_FILE = '@@PLUGINFILE@@/'

DUPLICATE_PROTECTION_SUFFIX = '_'

FILE_EXISTS = 0
SUCCESS = 1
FAILURE = -1
UNSUPPORTED = 2
UNKNOWN = 999

RESET_FLAG = '--reset'

#Track which content and html files have been created by
#this run of this program
content_created = set()
html_created = set()

#Class representing files in the Moodle system
#Used to track when a file has been located
#Supports multiple names (aliases) and multiple contexts
class MoodleFile:
    def __init__(self, hash, name, context_id):
        #dict mapping original names to names
        self.names = {name : name}
        self.initial_name = name
        # self.id = id
        self.hash = hash
        self.context_ids = {context_id}
        self.dir = None

    #Add another context ID
    def add_context(self, context_id):
        self.context_ids.add(context_id)

    #Add an alias
    def add_name(self, name):
        self.names[name] = name

    #Call this once you've located the file
    #dir is the directory it's located in
    def locate(self, dir):
        self.dir = dir

    #Has the file been located?
    def located(self):
        return self.dir is not None

    #Copy the file to its new location
    def copy_over(self, destination):
        #Fail if file has not been located
        if not self.located():
            raise ValueError("File %s not found" % self.hash)
        for old_name in self.names:
            name = self.names[old_name]
            #Check for duplicates and make the copy
            new_name = os.path.join(destination, NEW_FILES_DIR, name)
            #In order to do this well, need to track where the file suffix is
            dot_index = name.rfind(".")
            if dot_index == -1:
                dot_index = len(name)
            else:
                dot_index -= len(name)
            changed = False
            while new_name in content_created:
                changed = True
                #Update both the file's name and the path being written
                new_name = new_name[:dot_index] + DUPLICATE_PROTECTION_SUFFIX\
                    + new_name[dot_index:]
                name = name[:dot_index] + DUPLICATE_PROTECTION_SUFFIX\
                    + name[dot_index:]
            if changed:
                #Update the name in self.names
                self.names[old_name] = name
            #Register as a created file, to prevent collisions
            content_created.add(new_name)
            #Actually do the copy
            if os.path.exists(new_name):
                #File already exists
                return False
            else:
                #Copy the file
                shutil.copyfile(os.path.join(self.dir, self.hash), new_name)
                return True

#Convert the given info into an HTML page
def make_html(aname, content, context_files = []):
    body = html.unescape(content)
    #Find embedded files and fix them up
    embedded_indices = set()
    while (index := body.find(MOODLE_PLUGIN_FILE)) != -1:
        #Get the file name
        findex = index + len(MOODLE_PLUGIN_FILE)
        quote_index = body.find('"', findex)
        #Unqoute the URL for the filename
        filename = urllib.parse.unquote(body[findex:quote_index])
        #Clean up the filename, in case it's of the form whatever.ext?stuff
        dot_index = filename.rfind('.')
        qmark_index = filename.rfind('?')
        if dot_index >= 0 and qmark_index > dot_index:
            #Truncate the filename
            filename = filename[:qmark_index]
            quote_index = body.rfind('?', qmark_index)
        #Figure out which file it is
        found = False
        for i in range(len(context_files)):
            if filename in context_files[i].names:
                #Found it!
                embedded_indices.add(i)
                #Replace the given urllibbit with a reference to the file
                body = body[:index] + os.path.join(NEW_FILES_DIR,\
                    context_files[i].names[filename]) + body[quote_index:]
                found = True
                break
        if not found:
            raise ValueError("File %s not found" % filename)
    #Append extra files as links
    links_started = False
    for i in range(len(context_files)):
        if not i in embedded_indices:
            #Add a link to this file
            if not links_started:
                links_started = True
                body += '<ul>'
            file = context_files[i]
            body += '\n<li><a href="%s">%s</a></li>' %\
                (os.path.join(NEW_FILES_DIR, file.names[file.initial_name]),\
                    file.initial_name)
    if links_started:
        body += '\n</ul>'
    #Now, mess with the head
    head = "<title>%s</title>" % aname
    #Check for latex in body
    if ('\(' in body and '\)' in body) or ('\[' in body and '\]' in body):
        #Activate MathJax
        head += ('\n<script src="https://polyfill.io/v3/polyfill.min.js?'
            'features=es6"></script>\n<script id="MathJax-script" async '
            'src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/'
            'tex-mml-chtml.js"></script>')
    return "<html>\n<head>%s</head>\n<body>%s</body>\n</html>" %\
        (head, body)

#Write an html file
def write_html(dest, name, type, content):
    #The HTML directory
    dir = os.path.join(dest, NEW_HTML_DIR)
    #Helpers for piecing together the file name and path
    def compile_fname():
        return "%s_%s.html" % (type, name)
    def compile_fpath():
        return os.path.join(dir, compile_fname())
    #If have pathvalidate, sanitize the name
    if HAS_PATHVALIDATE:
        name = pathvalidate.sanitize_filename(name)
    #Continually rename while the file already exists
    while compile_fpath() in html_created:
        name += DUPLICATE_PROTECTION_SUFFIX
    #This it the path we're going to work with
    path = compile_fpath()
    #Does the file already exist?
    if os.path.exists(path):
        #Code for already exists
        return FILE_EXISTS
    #Register the file
    html_created.add(path)
    #Write the file
    try:
        with open(path, 'w') as out:
            out.write(content)
        return SUCCESS
    except:
        print("Failed to write file %s" % compile_fname())
        return FAILURE

#Return a string representation of flt as a percentage to at most 2 places
def percentify(flt):
    return ('%.2f' % (flt * 100)).rstrip('0').rstrip('.') + '%'

#For natural sorting
def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split(r'(\d+)', text) ]

#Return a string representation of flt as a number with at most 2 places.
#Also return the word 'points' following it, unless it should be 'point'.
def pointify(flt):
    num = ('%.2f' % flt).rstrip('0').rstrip('.')
    if num == '1':
        return num + ' point'
    else:
        return num + ' points'

if __name__ == '__main__':
    #Get arguments
    if len(sys.argv) < 2:
        print("Usage: python3 moodle_backup_organize.py source [dest] "
            "[--reset]")
        sys.exit(0)

    #Extract the source
    source = sys.argv[1]
    #Extract the destination
    if len(sys.argv) >= 3 and not (len(sys.argv) == 3 and\
            sys.argv[-1] == RESET_FLAG):
        destination = sys.argv[2]
    else:
        #If not given, use source as destination
        destination = source
    #Check for reset flag
    if sys.argv[-1] == RESET_FLAG:
        reset = True
    else:
        reset = False

    #Create the new files and content directories
    new_files_dir = os.path.join(destination, NEW_FILES_DIR)
    new_html_dir = os.path.join(destination, NEW_HTML_DIR)
    #Reset if necessary
    if reset:
        if os.path.isdir(new_files_dir):
            shutil.rmtree(new_files_dir)
        if os.path.isdir(new_html_dir):
            shutil.rmtree(new_html_dir)
    #Create if necessary
    if not os.path.isdir(new_files_dir):
        os.mkdir(new_files_dir)
    if not os.path.isdir(new_html_dir):
        os.mkdir(new_html_dir)

    #Create a link to files inside html
    files_link = os.path.join(new_html_dir, NEW_FILES_DIR)
    if not os.path.islink(files_link):
        os.symlink(os.path.abspath(new_files_dir), files_link)

    #Load the files
    files = dict()
    files_by_context = dict()
    ftree = etree.parse(os.path.join(source, FILES_XML))
    froot = ftree.getroot()

    for file_entry in froot:
        # #Get the file's ID
        # id = file_entry.attrib['id']
        #Get the file's hash, name, and context id
        hash = file_entry.find('contenthash').text
        name = file_entry.find('filename').text
        context_id = file_entry.find('contextid').text

        #Has this file been found already?
        if hash in files:
            #Yes
            #Just add a new name and context
            files[hash].add_name(name)
            files[hash].add_context(context_id)
        else:
            #Add an entry to files for this file
            files[hash] = MoodleFile(hash, name, context_id)
            # #Add alias by ID
            # files[id] = files[hash]

    #Find the files
    old_files_dir = os.path.join(source, OLD_FILES_DIR)
    for entry in os.listdir(old_files_dir):
        full_entry = os.path.join(old_files_dir, entry)
        if os.path.isdir(full_entry):
            #Find the files in this directory
            for fentry in os.listdir(full_entry):
                if fentry in files:
                    #Process the found file!
                    file = files[fentry]
                    file.locate(full_entry)
                    created = file.copy_over(destination)
                    for name in file.names.values():
                        if created:
                            print("Copied file %s" % name)
                        else:
                            print("Did not copy file %s, already exists" % name)
                    #Track by context
                    for context_id in file.context_ids:
                        if context_id not in files_by_context:
                            files_by_context[context_id] = []
                        files_by_context[context_id].append(file)

    print()
    print("Done copying files!")

    #Next, extract the questions
    questions = dict()
    qtree = etree.parse(os.path.join(source, QUESTIONS_XML))
    qroot = qtree.getroot()

    #Iterate through question categories
    for question_category in qroot:
        questions_node = question_category.find("questions")
        #Iterate through questions
        for question_node in questions_node:
            #Extract info about it
            id = question_node.attrib['id']
            text = question_node.find('questiontext').text
            type = question_node.find('qtype').text
            #Store the info
            questions[id] = {'text' : text, 'type' : type}

            answer_node = question_node.find('plugin_qtype_%s_question' % type)
            if answer_node is not None:
                answers = answer_node.find('answers')
            else:
                answers = None
            #Handle essays separately
            if type == 'essay':
                template = answer_node.find('essay').\
                    find('responsetemplate').text
                if template is not None:
                    questions[id]['template'] = template
            elif answers is not None:
                questions[id]['answers'] = dict()
                for answer in answers:
                    #Extract answer info
                    answer_id = answer.attrib['id']
                    answer_text = answer.find('answertext').text
                    answer_fraction = answer.find('fraction').text
                    answer_feedback = answer.find('feedback').text
                    #Store answer info
                    questions[id]['answers'][answer_id] = dict()
                    adict = questions[id]['answers'][answer_id]
                    adict['text'] = answer_text
                    adict['fraction'] = answer_fraction
                    if answer_feedback is not None:
                        adict['feedback'] = answer_feedback
                #Special handling for numericals
                if type == 'numerical':
                    #Units not currently handled
                    #Tolerance
                    records_node = answer_node.find('numerical_records')
                    for record_node in records_node:
                        ans_id = record_node.find('answer').text
                        tolerance = record_node.find('tolerance').text
                        if tolerance is not None:
                            adict = questions[id]['answers'][ans_id]\
                                ['tolerance'] = tolerance



    #Now do the page's contents
    ctree = etree.parse(os.path.join(source, CONTENT_XML))
    #Get the root of the content we care about
    croot = ctree.getroot().find("information").find("contents").\
        find("activities")

    for activity in croot:
        #Get the module name and directory
        mname = activity.find('modulename').text
        mdir = os.path.join(source, activity.find('directory').text)

        #Now, load the activity's XML
        atree = etree.parse(os.path.join(mdir, "%s.xml" % mname))
        #Get the root and the child we care about
        aroot = atree.getroot()
        achild = aroot.find(mname)

        #Get the activity's name and context ID
        aname = achild.find('name').text
        acontext = aroot.attrib['contextid']

        #Get the contextual files
        if acontext in files_by_context:
            context_files = files_by_context[acontext]
        else:
            context_files = []

        #print("Attempting to process %s %s" % (mname, aname))

        #Handle the various types
        success = UNKNOWN
        #Assignment, resource or folder
        if mname == ASSIGNMENT or mname == RESOURCE or mname == FOLDER:
            #Get the HTML content
            acontent = achild.find('intro').text
        #Page
        elif mname == PAGE:
            #Get the HTML content
            aintro = achild.find('intro').text
            acontent = achild.find('content').text
            if aintro is not None and len(aintro) > 0:
                acontent = aintro + "\n<br><br>\n" + acontent
        #URL
        elif mname == URL:
            #Get the URL content
            acontent = achild.find('externalurl').text
            #Convert to html
            acontent = '<a href="%s">%s</a>' % (acontent, aname)
        #Quiz
        elif mname == QUIZ:
            #Get the intro content
            aintro = achild.find('intro').text
            if aintro is not None and len(aintro) > 0:
                acontent = aintro + '\n<br><br>\n'
            else:
                acontent = ''
            #Process the questions
            question_nodes = dict()
            questions_node = achild.find('question_instances')
            for question_node in questions_node:
                #Get the ID, page, slot, and maxmark
                question_id = question_node.find('questionid').text
                page = int(question_node.find('page').text)
                slot = int(question_node.find('slot').text)
                points = question_node.find('maxmark').text
                #Store for later sorting
                question_nodes[(page, slot)] = {'id' : question_id,\
                    'points' : points}
            #Process the questions in order
            question_numbers = list(question_nodes.keys())
            question_numbers.sort()
            count = 1
            for question_number in question_numbers:
                #Re-extract the info
                question_node = question_nodes[question_number]
                question_id = question_node['id']
                #Get the question record
                question = questions[question_id]
                #Get the question type
                question_type = question['type']
                #Treat descriptions specially
                if question_type != 'description':
                    #Get the number of points
                    points = float(question_node['points'])
                    acontent += '<b>Question %d</b> (%s)<br>' % (count,\
                        pointify(points))
                    #Throw in the type
                    acontent += '[%s]' % question_type
                    #Increment the question counter
                    count += 1
                else:
                    acontent += '<b>Instructions:</b> '
                #Throw in the text
                acontent += '%s' % question['text']
                #Throw in template if it's there
                if 'template' in question:
                    acontent += '<br>Template: %s<br>' %\
                        question['template']
                #Process answers
                if 'answers' in question:
                    #Handle multichoice separately
                    if question_type == 'multichoice':
                        acontent += '<ol type="a">'
                    else:
                        acontent += '<ul>'
                    for answer_id in question['answers']:
                        answer = question['answers'][answer_id]
                        #Text
                        acontent += '<li>%s' % answer['text']
                        #Tolerance
                        if 'tolerance' in answer:
                            acontent += ' +/- %s' % answer['tolerance']
                        #Fraction
                        fraction = answer['fraction']
                        if fraction is not None:
                            #Format fraction as a two-decimal percent
                            acontent += " (%s)" % percentify(float(answer\
                                ['fraction']))
                        #Feedback
                        if 'feedback' in answer:
                            acontent += '<br><br>Feedback: %s' %\
                                answer['feedback']
                        #End list item
                        acontent += '</li>'
                    #End list
                    #Handle multichoice separately
                    if question_type == 'multichoice':
                        acontent += '</ol>'
                    else:
                        acontent += '</ul>'
                #Add in extra spacing
                acontent += '<br>\n'
        #Other (ignore)
        else:
            #Report no copy
            success = UNSUPPORTED

        if success == UNKNOWN:
            #Actually try to do a write now
            try:
                #Fix up/finalize the HTML
                if acontent is None or len(acontent) == 0:
                    acontent = mname.capitalize()
                html_content = make_html(aname, acontent, context_files)
                #Do the write
                success = write_html(destination, aname, mname, html_content)
            except Exception as ex:
                print("\nException occurred: {0}\n".format(ex))
                success = FAILURE
        #Report on success/failure
        if success == SUCCESS:
            print("Processed %s %s" % (mname, aname))
        elif success == FAILURE:
            print("Failed to process %s %s" % (mname, aname))
        elif success == FILE_EXISTS:
            print("Did not process %s %s, already exists" % (mname, aname))
        elif success == UNSUPPORTED:
            print("Did not process %s %s, type not supported" %\
                (mname, aname))

    #Construct HTML index
    #Should work even if all files already existed
    print()
    print("Constructing HTML index")
    index = dict()
    for html_file in os.listdir(new_html_dir):
        #Check if HTML file
        if html_file[-5:] == '.html':
            #Find its title and type
            underscore_index = html_file.find('_')
            if underscore_index == -1:
                #What's this file doing here?
                continue
            type = html_file[:underscore_index]
            if type not in ACTIVITY_NAMES:
                #What's this file doing here?
                continue
            with open(os.path.join(new_html_dir, html_file), 'r') as html_in:
                content = html_in.read()
                title_index = content.find('<title>')
                title_index_2 = content.find('</title>')
                if title_index == -1 or title_index_2 == -1 or\
                        title_index_2 < title_index:
                    #What's this file doing here?
                    continue
                title = content[title_index + 7 : title_index_2]
            #Add the file to the index
            if ACTIVITY_NAMES[type] not in index:
                index[ACTIVITY_NAMES[type]] = []
            index[ACTIVITY_NAMES[type]].append((html_file, title))
    #Start creating the content
    content = '<html><head><title>'
    #Get the course name
    try:
        course_name = html.unescape(ctree.getroot().find("information").\
            find("original_course_fullname").text)
    except:
        course_name = "Moodle Site"
    content += 'Index for %s</title></head><body><h1>Index for %s</h1>' %\
        (course_name, course_name)
    #Process the index in sorted order
    types = list(index.keys())
    types.sort()
    for type in types:
        content += '<h2>%s</h2><ul>' % type
        #Process the files in order
        index[type].sort(key = lambda entry: natural_keys(entry[0]))
        for entry in index[type]:
            content += '\n<li><a href="%s">%s</a></li>' % entry
        content += '</ul>'
    content += '</body></html>'
    #Write the file
    with open(os.path.join(new_html_dir, INDEX_FILENAME), 'w') as html_out:
        html_out.write(content)
    print("Wrote %s" % INDEX_FILENAME)

    print()
    print("Done!")
