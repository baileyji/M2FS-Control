import sys
import unittest
sys.path.append(sys.path[0]+'/../bin/')
sys.path.append(sys.path[0]+'/../lib/')
import shoeAgent
from command import Command

class TestShoeAgent(unittest.TestCase):
    
    def setUp(self):
        self.agent = object.__new__(shoeAgent.ShoeAgent)
        self.agent.__init__()
    
    def tearDown(self):
        del self.agent
        self.reset_mock_callback()
    
    def test_initialize_logger(self):
        """ Test that the agent logger exists """
        import logging
        self.agent.initialize_logger(logging.DEBUG)
        self.assertIsInstance(self.agent.logger, type(logging.getLogger('foo')))
    
    def test_initialize_cli_parser(self):
        """ Test that the argument parser exists """
        import argparse
        self.assertIsInstance(self.agent.cli_parser, argparse.ArgumentParser)
    
    def test_get_cli_help_string(self):
        """ Test that the help string has been defined"""
        help_str=self.agent.get_cli_help_string()
        self.assertIsInstance(help_str,str)
        self.assertNotEqual(help_str, "Subclass should override to provide help")
    
    def test_add_additional_cli_arguments(self):
        """ Skip """
        self.skipTest('Partial coverage provided by test_initialize_cli_parser')

    def test_initialize_socket_server(self):
        """ TODO """
        self.skipTest('Low Priority')

    def test_listenOn(self):
        """ Verify returns a tuple consisting of a string and number """
        save_argv=sys.argv
        #sys.argv='/M2FS-Control/bin/shoeAgent.py', '--side','R', '-p', 10000]
        try:
            address=self.agent.listenOn()
            self.assertIsInstance(address, tuple)
            self.assertEqual(len(address),2)
            self.assertIsInstance(address[1],int)
            self.assertIsInstance(address[0],str)
        finally:
            sys.argv=save_argv

    def test_existing_command_socket_message_received_callback(self):
        """ Verify that new commands are not accepted when an existing command
        exists from the same source and that neither the command handler nor
        the worker thread state are queried"""
        source=object()
        cmd_str='command_name args'
        cmd2_str='some_other_command args'
        prior_command=Command(source,cmd_str)
        new_command=Command(source,cmd2_str)
        #Register a command from the source
        self.agent.commands=[prior_command]
        #Register a callback for the new command so we fail if it is called
        self.agent.command_handlers={self.agent.getCommandName(cmd2_str):
                lambda cmd:self.fail(msg='Callback should not be called')}
        #Patch the agent._getWorkerThreadState to fail if it gets called
        self.agent._getWorkerThreadState=lambda self,cmd:self.fail(msg='Callback should not be called')
        #Make the call
        self.agent.socket_message_received_callback(source, cmd2_str)
        #Commands should not have changed
        self.assertEqual(len(self.agent.commands),1)
        self.assertIs(self.agent.commands[0], prior_command)

    def test_blocked_command_socket_message_received_callback(self):
        """ 
        verify that a blocked command is added to the list with a response,
        and that neither the command handler nor the worker thread state are queried
        """
        source=object()
        cmd_str='command_name args'
        new_command=Command(source,cmd_str)
        #Block the command
        self.agent.block(new_command)
        #Register a hander to fail if the handler gets called
        self.agent.command_handlers={self.agent.getCommandName(cmd_str):
            lambda cmd:self.fail(msg='Callback should not be called')}
        #Patch the agent._getWorkerThreadState to fail if it gets called
        self.agent._getWorkerThreadState=lambda self,cmd:self.fail(msg='Callback should not be called')
        #Make the call
        self.agent.socket_message_received_callback(source, cmd_str)
        #Command should have been closed out properly
        self.assertEqual(len(self.agent.commands),1)
        self.assertTrue(self.agent.commands[0].reply.startswith('ERROR: Command is blocked.'))

    def test_query_no_worker_socket_message_received_callback(self):
        """ Verify that the command handler is called when no worker thread is 
        state exists for the command """
        source=object()
        self.agent.command_handlers={'command_name':self.mock_callback}
        #Make the call
        self.agent.socket_message_received_callback(source, 'command_name ?')
        #Command should have been closed out properly
        self.assertEqual(len(self.agent.commands),1)
        self.assertTrue(self.mock_callback_called)
    
    def test_query_worker_state_socket_message_received_callback(self):
        """ Verify that the command handler is not called
            and the state of the worker thread is reported """
        source=object()
        cmd_str='command_name ?'
        cmd_state='Mock state'
        #Register a hander to fail if the handler gets called
        self.agent.command_handlers={self.agent.getCommandName(cmd_str):
            lambda cmd:self.fail(msg='Callback should not be called')}
        #Register a thread state
        self.agent.set_command_state(self.agent.getCommandName(cmd_str),cmd_state)
        #Make the call
        self.agent.socket_message_received_callback(source, cmd_str)
        #Command should have been closed out properly with the mock state
        self.assertEqual(len(self.agent.commands),1)
        self.assertEqual(self.agent.commands[0].reply, cmd_state)
    
    def mock_callback(self, cmd):
        self.mock_callback_called=True
        self.mock_callback_called_with=(cmd,)
        
    def reset_mock_callback(self):
        self.mock_callback_called=False
        self.mock_callback_called_with=None

    def test_get_version_string(self):
        """ Test that the version string exists """
        help_str=self.agent.get_version_string()
        self.assertIsInstance(help_str,str)
        self.assertNotEqual(help_str, 'AGENT Base Class Version 0.1')

    def test_on_exit(self):
        self.skipTest("How to test?")

    def test_handle_connect(self):
        self.skipTest("How to test?")

    def test_handle_server_error(self):
        self.skipTest("How to test?")

    def test_update_select_maps(self):
        self.skipTest("Ughhh")

    

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestShoeAgent)
    unittest.TextTestRunner(verbosity=2).run(suite)