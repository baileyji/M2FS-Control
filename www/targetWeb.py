#!/usr/bin/env python
from flask import Flask, render_template, request, Response
from flask_wtf.csrf import CsrfProtect
from flask_wtf import Form
from wtforms import SelectMultipleField, SubmitField
from wtforms import validators
from m2fs.plate.summarize import generate_tlist_file, generate_summary_file
import sys, time, threading, os, re
sys.path.append(sys.path[0]+'/../lib/')
from m2fsConfig import m2fsConfig
from glob import glob
import plate

MAX_SELECT_LEN=30

app = Flask(__name__)
app.secret_key = 'development key'

def get_possible_targets():
    targets=[]
    _plateDir=os.getcwd()+os.sep+m2fsConfig.getPlateDir()
    files=glob(_plateDir+'*.plate')
    for file in files:
        if os.path.basename(file).lower()!='none.plate':
            try:
                p=plate.Plate(file)
                targets.append((file, p.name))
            except IOError:
                pass
    return targets

def tlist_filename():
    return 'targets.txt'

def summary_filename():
    return 'summary.txt'

def get_zip(platefiles):
    import zipfile, StringIO
    if not platefiles:
        return ''
    summary_lines, trecs=generate_summary_file(platefiles)
    tlist_lines=generate_tlist_file(trecs)
    
    o = StringIO.StringIO()
    zf = zipfile.ZipFile(o, mode='w')
    zf.writestr(tlist_filename(), ''.join(tlist_lines))
    zf.writestr(summary_filename(), ''.join(summary_lines))
    zf.close()
    o.seek(0)
    result = o.read()
    return result

class TargetSelect(Form):
    select_size=30
    targets = SelectMultipleField('Targets',
                                  validators=[validators.Required()])
    submit = SubmitField("Make Targetlist")

@app.route('/', methods=['GET', 'POST'])
def index():
    form = TargetSelect(request.form)
    form.targets.choices=get_possible_targets()
    form.select_size=min(len(form.targets.choices)+1, MAX_SELECT_LEN)
    if request.method == 'POST' and form.targets.data:
        data=get_zip(form.targets.data)
        return Response(data, mimetype="application/octet-stream",
                        headers={"Content-Disposition":
                                 "attachment;filename=selected.zip"})

    return render_template('targetlist.html', form=form)


def parse_cl():
    parser = argparse.ArgumentParser(description='Help undefined',
    add_help=True)
    parser.add_argument('-d','--dir', dest='dir',
                        action='store', required=False, type=str,
                        help='',default='./')
    return parser.parse_args()


if __name__ =='__main__':
    app.run(debug=True)





possible_targets=[('cpp', 'C++'), ('py', 'Python'), ('text', 'Plain Text')]

