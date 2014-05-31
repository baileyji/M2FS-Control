#!/usr/bin/env python
from flask import Flask, render_template, request, Response
from flask_wtf.csrf import CsrfProtect
from flask_wtf import Form
from wtforms import SelectMultipleField, SubmitField, BooleanField,RadioField
from wtforms import validators
import sys, time, threading, os, re
sys.path.append(sys.path[0]+'/../lib/')
sys.path.append(sys.path[0]+'/../')
from m2fsConfig import m2fsConfig
from glob import glob
from hole_mapper.plate import load_dotplate
from jbastro.astroLib import sexconvert

MAX_SELECT_LEN=30

TARGET_CACHE=[]
TARGET_CACHE_FILE='./targetweb.cache'

app = Flask(__name__, template_folder='../www/templates/',
            static_folder='../www/static/')

app.secret_key = 'development key'

ROTATOR_SETTING='-7.18'


def generate_tlist_file(platefiles):
    fields=[]
    
    file_lines=[]
    obsfmt=('{n:<3} {id:<30} {ra:<12} {de:<12} {eq:<11} {pmRA:<11} {pmDE:<11} '
    '{irot:<11} {rotmode:<11} {gra1:<11} {gde1:<11} {geq1:<11} '
    '{gra2:<11} {gde2:<11} {geq2:<11}')
    header=obsfmt.format(n='#',
                        id='ID',
                        ra='RA',
                        de='DE',
                        eq='Eq',
                        pmRA='pmRA',
                        pmDE='pmDE',
                        irot='Rot',
                        rotmode='Mode',
                        gra1='GRA1',
                        gde1='GDE1',
                        gra2='GRA2',
                        gde2='GDE2',
                        geq2='GEQ2',
                        geq1='GEQ1')

    file_lines.append(header+'\n')


    obsfmt=('{n:<3} {id:<30} {ra:<12} {de:<12} {eq:<11} {pmRA:<11.2f} '
    '{pmDE:<11.2f} {irot:<11} {rotmode:<11} {gra1:<11} {gde1:<11} {geq1:<11} '
    '{gra2:<11} {gde2:<11} {geq2:<11}\n')

    stds_listed=[]

    for f in platefiles:
        try:
            p=load_dotplate(f)
            if p.file_version=='0.1':
                raise Exception("Can't process v0.1"+f)
        except Exception, e:
            print 'Platefile Error: {}'.format(e)
            continue

        for f in p.fields:
            s=obsfmt.format(n=len(file_lines),
                            id=(p.name+':'+f.name).replace(' ', '_'),
                            ra=sexconvert(f.ra, ra=True, dtype=str),
                            de=sexconvert(f.dec, dtype=str),
                            eq=f.epoch,
                            pmRA=f.pm_ra,
                            pmDE=f.pm_dec,
                            irot=ROTATOR_SETTING,
                            rotmode='EQU',
                            gra1=sexconvert(0,dtype=str),
                            gde1=sexconvert(0,dtype=str),
                            gra2=sexconvert(0,dtype=str),
                            gde2=sexconvert(0,dtype=str),
                            geq2=0,
                            geq1=0)
                            
            file_lines.append(s)
            
            for t in f.standards:
                s=obsfmt.format(n=len(file_lines),
                                id=t.id.replace(' ', '_'),
                                ra=sexconvert(t.ra, ra=True, dtype=str),
                                de=sexconvert(t.dec, dtype=str),
                                eq=t.epoch,
                                pmRA=t.pm_ra,
                                pmDE=t.pm_dec,
                                irot=ROTATOR_SETTING,
                                rotmode='EQU',
                                gra1=sexconvert(0,dtype=str),
                                gde1=sexconvert(0,dtype=str),
                                gra2=sexconvert(0,dtype=str),
                                gde2=sexconvert(0,dtype=str),
                                geq2=0,
                                geq1=0)
                std_rec=obsfmt.format(n=0,
                                id=t.id.replace(' ', '_'),
                                ra=sexconvert(t.ra, ra=True, dtype=str),
                                de=sexconvert(t.dec, dtype=str),
                                eq=t.epoch,
                                pmRA=t.pm_ra,
                                pmDE=t.pm_dec,
                                irot=ROTATOR_SETTING,
                                rotmode='EQU',
                                gra1=sexconvert(0,dtype=str),
                                gde1=sexconvert(0,dtype=str),
                                gra2=sexconvert(0,dtype=str),
                                gde2=sexconvert(0,dtype=str),
                                geq2=0,
                                geq1=0)
                if std_rec not in stds_listed:
                    file_lines.append(s)
                    stds_listed.append(std_rec)

    return file_lines


def get_possible_targets():
    targets=[]
    _plateDir=os.path.join(os.getcwd(), m2fsConfig.getPlateDir())
    print 'Looking for plates in {}'.format(_plateDir)
    files=glob(_plateDir+'*.plate')
    for file in files:
        if os.path.basename(file).lower()!='none.plate':
            try:
                p=load_dotplate(file)
                targets.append((file, p.name))
            except IOError:
                pass
    return targets

def tlist_filename():
    return 'targets.txt'

def summary_filename():
    return 'summary.txt'

def get_zip():
    global TARGET_CACHE
    import zipfile, StringIO
    if not TARGET_CACHE:
        return ''

    tlist_lines=generate_tlist_file(TARGET_CACHE)
    
    o = StringIO.StringIO()
    zf = zipfile.ZipFile(o, mode='w')
    zf.writestr(tlist_filename(), ''.join(tlist_lines))
#    zf.writestr(summary_filename(), ''.join(summary_lines))
    zf.close()
    o.seek(0)
    result = o.read()
    return result

class TargetSelect(Form):
    targets = SelectMultipleField('Targets', validators=[validators.Required()])
    new= BooleanField('New list', default=False)
    submit = SubmitField("Get list")

@app.route('/', methods=['GET', 'POST'])
def index():
    global TARGET_CACHE
    form = TargetSelect(request.form)
    form.targets.choices=get_possible_targets()
    form.select_size=min(len(form.targets.choices)+1, MAX_SELECT_LEN)
    if request.method == 'POST' and form.targets.data:

        if form.new.data:
            TARGET_CACHE=[]
        else:
            try:
                with open(TARGET_CACHE_FILE,'a+r') as fp:
                    TARGET_CACHE=fp.readlines()
            except IOError:
                TARGET_CACHE=[]
        TARGET_CACHE+=[t for t in form.targets.data if t not in TARGET_CACHE]
        try:
            with open(TARGET_CACHE_FILE,'w') as fp:
                fp.write('\n'.join(TARGET_CACHE))
        except IOError:
            pass

        return Response(get_zip(), mimetype="application/octet-stream",
                        headers={"Content-Disposition": "attachment;"
                                 "filename=selected.zip"})

    return render_template('targetlist.html', form=form)


#def parse_cl():
#    parser = argparse.ArgumentParser(description='Help undefined',
#    add_help=True)
#    parser.add_argument('-d','--dir', dest='dir',
#                        action='store', required=False, type=str,
#                        help='',default='./')
#    return parser.parse_args()


if __name__ =='__main__':
    app.run(debug=True)


