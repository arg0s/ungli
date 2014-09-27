# -*- coding: utf-8 -*-

from flask import Flask, redirect, url_for, request, jsonify, json, abort, g
import os
from flask.ext.api import FlaskAPI, status, exceptions
from flask.ext.basicauth import BasicAuth
from flask_cors import CORS
from parse_rest.connection import register
from parse_rest.datatypes import Object
from parse_rest.user import User as ParseUser
from parse_rest.core import ResourceRequestBadRequest, ResourceRequestForbidden,\
    ResourceRequestNotFound, ResourceRequestLoginRequired
from werkzeug.datastructures import MultiDict

app = FlaskAPI(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['BASIC_AUTH_USERNAME'] = os.environ.get('AUTH_U', 'spam')
app.config['BASIC_AUTH_PASSWORD'] = os.environ.get('AUTH_P', 'eggs')

basic_auth = BasicAuth(app)

port = int(os.environ.get('PORT', 5000))

if port == 5000:
    app.debug = True

# Load up args from env and hop on to parse
# Load up from .env for foreman on heroku
register(os.environ.get('PARSE_APP_ID'), os.environ.get(
    'PARSE_APP_KEY'), master_key=os.environ.get('PARSE_SECRET_KEY'))

# Choices can be used for sessions as well as panels by attribution
# of appropriate options (yes/no or speaker1/speaker2/speaker3)
# TODO: pull from config instead

routes = {
    "08030752691": "Choice 1",
    "08030752692": "Choice 2",
    "08030752693": "Choice 3",
}


class Clap(Object):

    @classmethod
    def load(cls, obj):
        clap = Clap()
        obj = obj.to_dict()
        clap.tel = obj.get('From', None)
        route = obj.get('To', None)
        clap.created = obj.get('StartTime', None)
        if route is not None:
            clap.vote = routes.get(route, None)
        clap.save()
        return clap

    def to_dict(self):
        return dict(tel=self.tel, vote=self.vote)


class Performance(Object):
    pass


@app.route('/performance', methods=['GET', 'POST', ])
@basic_auth.required
def set_performance():
    if request.method == 'POST':
        name = request.data.get('name')
        session = Performance(name=name)
        session.save()
        return dict(id=session.id, name=session.name), status.HTTP_201_CREATED
    else:
        session = Performance.Query.all().limit(1).pop()
        return dict(id=session.id, name=session.name)


def get_feed(mask=True):

    def pub_tel(tel, mask):
        return tel.replace(tel[:7], 'X-XXX-XXX-') if mask else tel

    # Grab the users from parse, process them based on choices
    users = Clap.Query.all()
    # Load these into the werkzeug multidict since its possible there may be
    # multiple missed calls per number
    entries = MultiDict([(user.vote, pub_tel(user.tel, mask))
                         for user in users])
    # For now, collapse the multidict, retaining only unique items - simple
    # algo

    def count_votes(entries, choice):
        votes = list(set(entries.getlist(choice)))
        return dict(choice=choice, votes=votes, count=len(votes))

    votes = [count_votes(entries, choice)
             for choice in routes.values()]
    return votes


@app.route('/votes')
@basic_auth.required
def votes():
    return get_feed(mask=False)


@app.route('/stream')
def stream():
    return get_feed()


@app.route('/clap')
@basic_auth.required
def clap():
    session = Performance.Query.all().limit(1)
    if len(session) is 0:
        session = Performance(name='Keynote')
        session.save()
    else:
        session = session.get()
    try:
        # Accepts an incoming missed call log
        # Logs the entry to Parse
        user = Clap.load(request.args)
        user.session = session
        user.save()
        return user.to_dict()
    except ResourceRequestBadRequest as e1:
        print(e1)
        # TODO: do something more useful here
        pass
    except Exception as e:
        # TODO: do something more useful here
        print(e)
        pass
    # Ensure the drop off happens
    return dict(status=True)

if __name__ == "__main__":

    app.run(port=port)
