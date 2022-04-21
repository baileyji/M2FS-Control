#!/usr/bin/env python2.7
import time
from flask import Flask, render_template, request, Response, make_response, redirect
from flask_wtf.csrf import CsrfProtect
from flask_wtf import Form
from wtforms import SelectMultipleField, SubmitField, BooleanField, RadioField
from wtforms import DecimalField, validators

import hole_mapper.pathconf
from hole_mapper.platedata import get_metadata, get_all_plate_names
from jbastro.astrolibsimple import sexconvert

from flask import send_file
import StringIO, datetime

import logging

def setup_logging(loglevel=logging.DEBUG):
    log = logging.getLogger()
    log.setLevel(loglevel)

hole_mapper.pathconf.run_params_dir='./plates/plates'
hole_mapper.pathconf.m2fs_params_dir='./plates/configs'
hole_mapper.pathconf.setups_dir='./plates/setups'
hole_mapper.pathconf.output_dir='./plates/output'

setup_logging()
_log=logging.getLogger()

MAX_SELECT_LEN=30

TARGET_CACHE=[]
TARGET_CACHE_FILE='./targetweb.cache'

#Go ahead and call this to save time when the page is accessed the first time
_log.info('Preloading all plates')
tic=time.time()
get_metadata('', cachefile=TARGET_CACHE_FILE)
toc=time.time()
_log.info('Preloading finished in {:.0f} seconds.'.format(toc-tic))

app = Flask(__name__, template_folder='../www/templates/',
            static_folder='../www/static')

app.secret_key = 'development key'

ROTATOR_SETTING=-7.24


def generate_tlist_file(platefiles, rotator=ROTATOR_SETTING, n0=1,sn0=1):

    rot='{:.2f}'.format(rotator)

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
    ndx=n0
    stdndx=sn0
    pmetadata=get_metadata(platefiles, cachefile=TARGET_CACHE_FILE)
    for pf,p in zip(platefiles,pmetadata):

        if p is None:
            file_lines.append('Error with plate {}'.format(pf))
            continue

        for f in p.fields:
            id=(p.name+':'+f.name).replace(' ', '_').replace(':', '_')
            s=obsfmt.format(n=ndx,
                            id=id,
                            ra=sexconvert(f.ra, ra=True, dtype=str),
                            de=sexconvert(f.dec, dtype=str),
                            eq=f.epoch,
                            pmRA=f.pm_ra,
                            pmDE=f.pm_dec,
                            irot=rot,
                            rotmode='EQU',
                            gra1=sexconvert(0,dtype=str),
                            gde1=sexconvert(0,dtype=str),
                            gra2=sexconvert(0,dtype=str),
                            gde2=sexconvert(0,dtype=str),
                            geq2=0,
                            geq1=0)

            file_lines.append(s)
            ndx+=1

        file_lines.append('\n')

    file_lines.append('#Standards \n\n')
    for pf,p in zip(platefiles,pmetadata):

        if p is None:
            file_lines.append('Error with plate {}'.format(pf))
            continue

        for f in p.fields:
            for t in f.standards:
                s=obsfmt.format(n=stdndx,
                                id=t.id.replace(' ', '_'),
                                ra=sexconvert(t.ra, ra=True, dtype=str),
                                de=sexconvert(t.dec, dtype=str),
                                eq=t.epoch,
                                pmRA=t.pm_ra,
                                pmDE=t.pm_dec,
                                irot=rot,
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
                                irot=rot,
                                rotmode='EQU',
                                gra1=sexconvert(0,dtype=str),
                                gde1=sexconvert(0,dtype=str),
                                gra2=sexconvert(0,dtype=str),
                                gde2=sexconvert(0,dtype=str),
                                geq2=0,
                                geq1=0)
                if std_rec not in stds_listed:
                    file_lines.append(s)
                    stdndx+=1
                    stds_listed.append(std_rec)

    return file_lines

class TargetSelect(Form):
    targets = SelectMultipleField('Targets')#, validators=[validators.Required()])
    rot = DecimalField(default=ROTATOR_SETTING, label='Rotator setting')
    tnum = DecimalField(default=1, places=0, label='Starting Target Number')
    snum = DecimalField(default=1, places=0, label='Starting Standard Number')
    submit = SubmitField("Get list")


page = """<!DOCTYPE html>
<html><head>
        <title>M2FS Targetlist Generator</title>
        <strong><link rel="stylesheet" href="/static/css/main.css"></strong></head>
<body>
<header><div class="container"><h1 class="logo">M2FS</h1></div></header>
<div class="container">
<h1>Select Targets</h1>
<form method="POST" action="/targetlist">
    {targ}
    <br>
    <label for="rot">Rotator setting</label> <input id="rot" name="rot" type="text" value="-7.24">
    <br>
    <label for="tnum">Starting Target Number</label> <input id="tnum" name="tnum" type="text" value="1">
    <br>
    <label for="snum">Starting Standard Number</label> <input id="snum" name="snum" type="text" value="1">
    <input id="submit" name="submit" type="submit" value="Get list">
</form></div></body></html>"""


@app.route('/', methods=['GET', 'POST'])
@app.route('/targetlist', methods=['GET', 'POST'])
def index():
    platedict=get_all_plate_names(cachefile=TARGET_CACHE_FILE)
    logging.getLogger(__name__).info('Fetched {} plate names'.format(len(platedict)))
    form = TargetSelect()
    form.targets.choices=zip(platedict,platedict)
    form.select_size=min(len(platedict)+1, MAX_SELECT_LEN)

    #return foo.format(targ=form.targets(size=form.select_size, multiple=True))

    #logging.getLogger('TWeb').info('Form sized {}'.format(str(form.targets(size=form.select_size, multiple=True))))
    #print form.validate_on_submit()

    if request.method == 'POST' and form.targets.data:

        TARGET_CACHE=[t for t in form.targets.data]

        fn='M2FS{}.cat'.format(datetime.datetime.now().strftime("%B%Y"))

        dat=StringIO.StringIO(''.join(generate_tlist_file(TARGET_CACHE,
                                                          rotator=form.rot.data,
                                                          n0=form.tnum.data,
                                                          sn0=form.snum.data)))
        dat.seek(0)

        return send_file(dat, mimetype='text/plain',
            attachment_filename=fn,as_attachment=False)

    return page.format(targ=form.targets(size=form.select_size, multiple=True))


if __name__ =='__main__':
    app.run(host='0.0.0.0',port=8080,debug=False)
