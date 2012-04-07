#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import serial
import sys
import select

MAX_CLIENTS=2
VERSION_STRING='0.1'

#http://stackoverflow.com/questions/5943249/python-argparse-and-controlling-overriding-the-exit-status-code
class ArgumentParser(argparse.ArgumentParser):    
    def _get_action_from_name(self, name):
        """Given a name, get the Action instance registered with this parser.
        If only it were made available in the ArgumentError object. It is 
        passed as it's first arg...
        """
        container = self._actions
        if name is None:
            return None
        for action in container:
            if '/'.join(action.option_strings) == name:
                return action
            elif action.metavar == name:
                return action
            elif action.dest == name:
                return action

    def error(self, message):
        exc = sys.exc_info()[1]
        if exc:
            exc.argument = self._get_action_from_name(exc.argument_name)
            raise exc
        super(ArgumentParser, self).error(message)

    def exit(self,*args,**kwargs):
        pass
        
        
class test():

    def __init__(self):
        pass
        
        
    def configure_command_parser(self):
        #Create a parser for commands
        self.command_parser=ArgumentParser(description='Command Parser',
                                           add_help=True)
        subparsers = self.command_parser.add_subparsers(dest='command_name',
                                               help='sub-command help')
        #commands command
        subparsers.add_parser("commands", help="Return a list of commands")
        #TD command
        td=subparsers.add_parser("TD", help="Tell Position of tetris")
        td.add_argument('tetrisID',choices='ABCDEFGH',
                        help='The tetris to command')
        #DP command
        dp=subparsers.add_parser("DP", help="Define Position of tetris")
        dp.add_argument('tetrisID',choices='ABCDEFGH',
                        help='The tetris to command')
        dp.add_argument('pos', type=int,
                        help='The position to define as 0 \
                             (default: the current position)')

    def configure_command_parser2(self)
        # create the top-level parser
        parser = argparse.ArgumentParser(prog='PROG')
        parser.add_argument('--foo', action='store_true', help='foo help')
        subparsers = parser.add_subparsers(help='sub-command help')
        
        # create the parser for the "a" command
        parser_a = subparsers.add_parser('a', help='a help')
        parser_a.add_argument('bar', type=int, help='bar help')
        
        # create the parser for the "b" command
        parser_b = subparsers.add_parser('b', help='b help')
        parser_b.add_argument('--baz', choices='XYZ', help='baz help')
        
        # parse some argument lists
        parser.parse_args(['a', '12'])
        Namespace(bar=12, foo=False)
        >>> parser.parse_args(['--foo', 'b', '--baz', 'Z'])
        Namespace(baz='Z', foo=True)
                             

if __name__=="__main__":

    x=test()
    x.configure_command_parser();
    