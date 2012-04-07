#!/opt/bin/python2.7
import argparse
VERSION_STRING='1.0'

def reportCommands():
    print "reporting commands"

def tellPosition():
    print "telling position"

def definePosition():
    print "defining position"    
    

def main():
	
    helpdesc='test help description'
    
	#Create a command parser with the default agent commands
    cli_parser = argparse.ArgumentParser(
                description=helpdesc,
                add_help=True)
    cli_parser.add_argument('--version',
                            action='version',
                            version=VERSION_STRING)
    cli_parser.add_argument('-p','--port', dest='PORT',
                            action='store', required=False, type=int,
                            help='the port on which to listen')
    cli_parser.add_argument('-d','--daemon',dest='DAEMONIZE',
                            action='store_true', default=False,
                            help='Run agent as a daemon')
    
    cli_parser.add_argument('command',nargs='*',
                            help='Agent command to execute') 
    
    
    
    #parse the args to grab a port, if found listen for connections
    args=cli_parser.parse_args()
    
    print args.command
    
    
    command_parser=argparse.ArgumentParser(description='',add_help=True)
    
                
    
    subparsers = command_parser.add_subparsers(dest='command_name',
                                               help='sub-command help')
    
    command_list=[
            ("commands",
             {'name':"commands",
              'help':"Return a list of commands"},
             reportCommands),
            ("TD",
             {'name':"TD",
              'help':"Tell Position - Tell position of tetris"},
             tellPosition),
            ("DP",
             {'name':"DP",
              'help':"Define Position - Define the current position of tetris"},
             definePosition)
            ]
    
    command_callbacks={l[0]:l[2] for l in command_list}

    subcommand_parsers={}
    for name,argparse_dict,callback in command_list:
        subcommand_parsers[name] = subparsers.add_parser(**argparse_dict)


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

    parsed_comm=command_parser.parse_args(args.command)
    
    print args
    print parsed_comm
    
    command_callbacks[parsed_comm.command_name]()


if __name__ == "__main__":
    main()
