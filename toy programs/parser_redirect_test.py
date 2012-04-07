import sys
import argparse
from cStringIO import StringIO



#Create a parser for commands
command_parser=argparse.ArgumentParser(description='',
                                            add_help=True)
subparsers = command_parser.add_subparsers(dest='command_name',
                                       help='sub-command help')
add_command_parser=subparsers.add_parser

#configure specialized agent command parsing
command_list=[
        ("commands",
         {'name':"commands",
          'help':"Return a list of commands"}),
        ("TD",
         {'name':"TD",
          'help':"Tell Position - Tell position of tetris"}),
        ("DP",
         {'name':"DP",
          'help':"Define Position - Define the current position of tetris"})
        ]

subcommand_parsers={}
for name,argparse_dict in command_list:
    subcommand_parsers[name] = add_command_parser(**argparse_dict)

subcommand_parsers['TD'].add_argument('tetrisID',
                            choices='ABCDEFGH',
                            help='The tetris to command')
subcommand_parsers['DP'].add_argument('tetrisID',
                            choices='ABCDEFGH',
                            help='The tetris to command')
subcommand_parsers['DP'].add_argument(
        'pos', type=int,
        help='The position to define as 0 \
              (default: the current position)'
        )
print "HI"

message_str='Tads'
#command=command_parser.parse_args(message_str)
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = mystdout = StringIO()
sys.stderr = mystderr = StringIO()
try:
    command=command_parser.parse_args(message_str)
except Exception, err:
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    print "Exception %s" % s
finally:
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    print "Mystdout %s" % mystdout.getvalue()
    print "Mystderr %s" % mystderr.getvalue()