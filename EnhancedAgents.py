from autogen import AssistantAgent, UserProxyAgent, Agent
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
import os

# Default directory for storing agent memories
MEMORY_DIRECTORY = "Managed_Memories"

# Memory Enabled Agent(MEA)/Memory front-end - this is the object instanced in main
class MemoryEnabledAgent(AssistantAgent):
    
    # Portion of MEA system prompt - appended after DEFAULT_SYSTEM_MESSAGE. Responsible for ensuring discussion benefits from short term memory (STM)
    DEFAULT_MEM_AGENT_MESSAGE = """
    
    Be sure to modulate your discussion by what you remember about {sender}.
    If something is missing that you should know, try checking your memory using lookup_from_long_term_memory and pass in a hint describing what you are trying to remember.
    If you are asked what can you remember, it would be good to call lookup_from_long_term_memory.
    """
    
    # Other portion of MEA system prompt - this should be modified for the task at hand for the MEA
    DEFAULT_SYSTEM_MESSAGE = """   """
    
    #--------- Dynamic Memory Settings -----------
    # Consult documentation before adjusting from defaults - Bad values can cause infinite looping/AI calls/$$
    # Max number of short term memories before initiating compression to long
    DEFAULT_SHORT_TERM_MEMORY_LIMIT = 10
    
    # Proportion to cut short term memory off (0.9 drops 9 out of 10 memories after exceeding STM limit, 0.1 drops 1 out of 10 memories after exceeding STM limit)
    DEFAULT_COMPRESSION_RATIO_STM = 0.8
    
    # Max convo length before the end starts falling off, in number of messages. User and AI both count, so minimum is 2.
    DEFAULT_MAX_CONVO_LENGTH = 10
    
    # Proportion to cut chat off (0.9 drops 9 out of 10 chats after exceeding limit, 0.1 drops 1 out of 10 chats after exceeding limit)
    DEFAULT_COMPRESSION_RATIO_CHAT = 0.8
    
    def __init__(self, name, gpt_config):
        # Grab GPT params for other agents
        self.gpt_config = gpt_config
        self.llm_config = gpt_config['config_list']
        self.config_list = gpt_config['config_list']
        self.llm_model = gpt_config['config_list'][0]['model']
        
        # Regular __init__ for AssistantAgent
        super().__init__(
            name = name,
            llm_config = {
            "temperature": 0,
            "request_timeout": 600,
            "seed": 42,
            "model": self.llm_model,
            "config_list": self.config_list,
            "functions": [
                    {
                        "name": "lookup_from_long_term_memory",
                        "description": "Retrieves information from the long term memory; Do not use this function without first referring to Your current short term memory. Use this function to recall something outside the scope of your context. These are your older memories.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "hint": {
                                    "type": "string",
                                    "description": "A hint or description of what information is being attempted to be retrieved.",
                                },
                            },
                            "required": ["hint"],
                        },
                    },
                    
                ],
            },
            # Full system prompt is: {Task instructions} + {Reminder to consider memories}
            system_message = self.DEFAULT_SYSTEM_MESSAGE + self.DEFAULT_MEM_AGENT_MESSAGE 
        )
        
        # Path to directory containing specific MEA instance memories
        self.memories_path = os.path.join(MEMORY_DIRECTORY, self.name)
        
        # Paths to short term and long term memory files
        self.short_term_memory_path = os.path.join(self.memories_path,"short_term_memory.txt")
        self.long_term_memory_path = os.path.join(self.memories_path,"long_term_memory.txt")
        
        # Initialize memories
        self.memories = self.initialize_memories()
        
        # Initialize Memory Manager Agent (MMA) - tie it into MEA object
        self.memory_manager = self.initialize_memory_manager()
        
        # Functions that must be callable by MEA when conversing with UserProxyAgent
        self.functions_for_map = [self.lookup_from_long_term_memory]
        
        # Initialize placeholder for remembering who MEA is conversing with - only initialized once per chat.
        self.sender_agent = None
        
    # Mostly Copy/Paste from AutoGen standard AssistantAgent. Need to override receive in such a way that the chat length on the agents side stays small/under max/follows memory logic
    def receive(
        self,
        message: Union[Dict, str],
        sender: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        """Receive a message from another agent.

        Once a message is received, this function sends a reply to the sender or stop.
        The reply can be generated automatically or entered manually by a human.

        Args:
            message (dict or str): message from the sender. If the type is dict, it may contain the following reserved fields (either content or function_call need to be provided).
                1. "content": content of the message, can be None.
                2. "function_call": a dictionary containing the function name and arguments.
                3. "role": role of the message, can be "assistant", "user", "function".
                    This field is only needed to distinguish between "function" or "assistant"/"user".
                4. "name": In most cases, this field is not needed. When the role is "function", this field is needed to indicate the function name.
                5. "context" (dict): the context of the message, which will be passed to
                    [Completion.create](../oai/Completion#create).
            sender: sender of an Agent instance.
            request_reply (bool or None): whether a reply is requested from the sender.
                If None, the value is determined by `self.reply_at_receive[sender]`.
            silent (bool or None): (Experimental) whether to print the message received.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.
        """
        
        # Read short term memory file
        self.memories = self.read_short_term_memory()
        
        # Default AutoGen function
        self._process_received_message(message, sender, silent)
               
        # If there is more than the initial message
        if len(self.chat_messages[sender]) > 1:
            # Construct the STM message to be placed at top of context
            m0 = {}
            m0['content']="Things you remember about {sender}: {short_term_memories}|".format(short_term_memories = self.memories, sender = self.sender_agent.name)
            m0['role']='assistant'
            
            # Overwrite top of context with STM
            self.chat_messages[sender][0] = m0
        
        # If there is only the initial message - only at chat initialization
        else: 
            # set sender_agent to sender, and format MEA system prompt to senders name
            self.sender_agent = sender # safe to set here
            self.system_message.format(sender=self.sender_agent.name)
            
        
        # Debugging callouts for monitoring chat progression/dynamics
        print("DEBUG: NumChatMessages: " + str(len(self.chat_messages[sender])) + " vs Limit:" + str(self.DEFAULT_MAX_CONVO_LENGTH))
        print("DEBUG: ChatMessages:")
        print(self.chat_messages[sender])
        print("END DEBUG")
        
        # If max length is hit, use compression ratio to trim window and then pass history to memory manager
        # Remove the oldest message, but not the first! First message is dynamic short term memory
        if self.chat_too_long():
            # index 0 is short term memory, index 1 is start of conversation, and where to do FILO
            # use compression ratio to determine trim number
            trim_num = int(len(self.chat_messages[sender])*self.DEFAULT_COMPRESSION_RATIO_CHAT)
            lost_messages = []
            
            # pop corresponding messages out of chat history
            for i in range(trim_num-1):
                lost_messages.append(self.chat_messages[sender].pop(1))
            
            # send messages to memory manager to process
            self.memory_manager.process_chat_section(lost_messages)
            
            # Debugging callouts for monitoring chat message trimming
            print(f"DEBUG: Messages trimmed from chat:\n{lost_messages}")

        # Default AutoGen Logic
        if request_reply is False or request_reply is None and self.reply_at_receive[sender] is False:
            return   
        reply = self.generate_reply(messages=self.chat_messages[sender], sender=sender)
        if reply is not None:
            self.send(reply, sender, silent=silent)
    
    # Initilize memory structure and MEA memories.
    def initialize_memories(self):
        # Does a memory directory exist? If not, make one
        if not os.path.exists(MEMORY_DIRECTORY):
            os.makedirs(MEMORY_DIRECTORY)
        
        # Does this specific agents memory exist? 
        if os.path.exists(self.memories_path):
            return self.read_short_term_memory()
        
        # If not, initialize the memory folder and files
        else:
            os.makedirs(self.memories_path)
            with open(self.long_term_memory_path, 'w') as f:
                pass
                
            with open(self.short_term_memory_path, 'w') as f:
                pass
                
            return None
                
    # Initialize the MEA's memory manager agent, pass in MEA object.
    def initialize_memory_manager(self):
        return MemoryEnabledAgent_Manager(parent_agent = self)
    
    # Check if chat is exceeding limits - return True if true, False otherwise
    def chat_too_long(self):
        # Remove function calls when they are seen, but NOT 'role' = function messages. It looks like that is the response/return value. But 'function_call' is purely the call and shouldn't really count or exist in chat.
        all_chats = self.chat_messages[self.sender_agent]
        filtered_chats = [c for c in all_chats if 'function_call' not in c]
        self.chat_messages[self.sender_agent] = filtered_chats
        
        # Length logic.
        if len(self.chat_messages[self.sender_agent]) > self.DEFAULT_MAX_CONVO_LENGTH:
            return True
        else:
            return False
    
    # Read and return short term memories, either as string or list.
    def read_short_term_memory(self, list_mode = False):
        # Standard mode returns a joined string of memories
        if not list_mode:
            with open(self.short_term_memory_path,'r') as f:
                memories = '|'.join(f.readlines())
            
            # Store memories for consistent updated viewing.
            return memories
            
        # List_mode is used if the memories should be returned as a list instead of a joined string - used by memory manager
        else:
            with open(self.short_term_memory_path,'r') as f:
                return f.readlines()[0].split('|')
    
    # Append new short term memories to STM file.
    def append_to_short_term_memory(self, memories):
        with open(self.short_term_memory_path,'a') as f:
            for memory in memories:
                if memory != None:
                    f.write(f"{memory}|")
                    
        # Check if new additions cause STM to exceed limit
        if self.short_term_memory_full():
            # Debugging messages to monitor memory compression
            print("DEBUG")
            print("ATTEMPTING MEMORY COMPRESSION")
            print("END DEBUG")
            
            # TODO: add the summary of the stored memories to the bottom of short term using s_to_l_response. For now, return True
            # BEWARE - bad settings could get you stuck in a loop, such as a minimal compression ratio
            s_to_l_response = self.short_term_to_long_term()
            print(s_to_l_response)
            return True

        return True
    
    # Logic for checking if short term memory has filled
    # TODO: Catch None, "", and other pointless memories. Rewrite file to eliminate them and don't consider them in count.
    def short_term_memory_full(self):
        with open(self.short_term_memory_path,'r') as f:
            num_memories = len(f.readlines()[0].split('|'))
            
        if num_memories > self.DEFAULT_SHORT_TERM_MEMORY_LIMIT:
            return True
        else:
            return False
    
    # Call memory compression routine on STM - trim off some (FILO) - request memory manager to store it.    
    def short_term_to_long_term(self):

        # memory manager rewrites the memory as normal, but without the trimmed off ones.
        # TODO: include a short statement/comment/line, very free form, that captures the "feeling" of the memories that just got tucked away. Add it to STM as supplicant for those lost in compression.
        return self.memory_manager.short_to_long()
    
    # Attempt to retrieve information from LTM as it relates to a hint.
    def lookup_from_long_term_memory(self, hint):
        # Pass request on to MMA.
        return self.memory_manager.lookup_from_long(hint)
        
    # Called by memory manager to reset short term memory after compression. Can be used to completely rewrite STM.
    def rewrite_short_term_memory(self, memories):
        with open(self.short_term_memory_path, 'w') as f:
            for memory in memories:
                f.write(f"{memory}|")

    # Get the function map to return to user proxy
    def get_function_map(self):
        f_map = {}
        f_list = self.llm_config["functions"]
        for i in range(len(f_list)):
            f_map[f_list[i]['name']] = self.functions_for_map[i]
    
        return f_map
        



# MEA Memory Manager/Memory back-end - this object is unseen to whoever the MEA is conversing/working with.
# TODO: All LTM operations require user to manually 'exit', or things get weird. Need to fix it for automated execution and chat exiting
class MemoryEnabledAgent_Manager(AssistantAgent):
    # How to remember, essentially. This is an engineered prompt. It can be changed, but consider the utility being requested and ensure some semblence remains.
    DEFAULT_MEM_MANAGER_MESSAGE = """
    You are a helpful AI assistant acting as a memory manager. There are three situations where you will be asked to perform:
    
    1. Summarize conversation section
    You will be shown a section of conversation as it leaves the context window of another assistant. You are to extract key points, facts, or memories, from the section of conversation which will then be added to the memory of the other assistant. It is critical that you are detail oriented so you do not miss anything.
    
    When you are shown a section of conversation, make a function call to append_to_short_term_memory and pass in a list of facts/statements/anything that accuractly and succinctly covers all details.
    
    
    2. Incorporate information into long-term memory
    You will be shown the existing long term memory, and a list of new memories which need to be incorporated. The memory is formatted as a series of statements seperated by the '|' character.
    For example, the existing memory might look like this:
        "{User's name} is allergic to seafood| {User's name} likes dogs| {User's name} is from Canada" 
    In this example, if you were requested to write a message to memory that was "{User's name} likes cats", when you go to rewrite the memory, it should look like this:
        "{User's name} is allergic to seafood| {User's name} likes dogs, cats| {User's name} is from Canada"
    Sometimes it might be best to remove content from the memory. For example, if the existing memory looked like this:
        "{User's name} is allergic to seafood| {User's name} likes dogs, cats| {User's name} is from Canada"
    And you were asked to write a message to memory that was "User does not like dogs", when you go to rewrite the memory, it should look like this:
        "{User's name} is allergic to seafood| {User's name} likes cats| {User's name} is from Canada"
    The changes to the rewritten memory can span multiple statements, if appropriate. The point is to keep the entire memory as accurate and representative as possible.
    
    3. Retrieve information from long-term memory
    You will be shown the existing long term memory, and be asked by the agent "What do I know about {thing}?". The agent is trying to find any information in its memory about {thing}. You should respond with a simple statement that answers the question.
    
    Do not participate in any form of conversation.
    
    If you do not know something, say 
        "I don't know anything about {}  
        
        TERMINATE"
        
    After you have finished your task, respond with "TERMINATE"

    """
    
    # Unused
    DEFAULT_SYSTEM_MESSAGE = """ This one is more about the task at hand for the agent """


    def __init__(self, parent_agent):
        # Grab parent agent object and parent agent llm config info.
        self.parent_agent = parent_agent
        self.gpt_config = parent_agent.gpt_config
        self.llm_config = self.gpt_config['config_list']
        self.config_list = self.gpt_config['config_list']
        self.llm_model = self.gpt_config['config_list'][0]['model']
        
        # Regular __init__ for AssistentAgent
        super().__init__(
            name= parent_agent.name + "_MemoryManager",
            llm_config={
                "temperature": 0,
                "request_timeout": 600,
                "seed": 42,
                "model": self.llm_model,
                "config_list": self.config_list,
                "functions": [
                    {
                        "name": "rewrite_memory",
                        "description": "Rewrites the entire memory to incorporate new information in a smart, condensed, entity focused way.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "memories": {
                                    "type": "string",
                                    "description": "the rewritten memory. Contains all the information from existing memory as well as the new information.",
                                },
                            },
                            "required": ["memories"],
                        },
                    },
                    {
                        "name": "append_to_short_term_memory",
                        "description": "Writes an array of items to memory.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "memories": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "description": "thing or things to record and remember. Make sure each string is context complete, such that an outsider would understand it."
                                    },
                                },
                            },
                            "required": ["memories"]
                        }
                    },
                    
                    
                ],
            },
            system_message = self.DEFAULT_MEM_MANAGER_MESSAGE,
        )
        
        # These are dummy user_agents to allow MMA code execution. There needs to be two as conversation histories were cross-contaminating on consequetive function calls.
        self.function_agent_LTM = UserProxyAgent(
            name="user_proxy_for_LTM",
            is_termination_msg= self.is_mem_termination_msg,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config={"work_dir": "_test"},
            function_map={"rewrite_memory": self.rewrite_memory}
            )
        self.function_agent_STM = UserProxyAgent(
            name="user_proxy_for_STM",
            is_termination_msg= self.is_mem_termination_msg,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config={"work_dir": "_test"},
            function_map={"append_to_short_term_memory": self.parent_agent.append_to_short_term_memory}
            )
    
    # Function to automate LTM/STM operations
    def is_mem_termination_msg(self, msg):
        if msg.get("content") != None:
            if msg.get("content", "").rstrip().endswith("TERMINATE"):
                return True
        return False
        
    
    # Present the memory manager with the lost messages to summarize into parent agents short term memory. Will call append_to_short_term_memory in parent MEA and pass in memories.
    def process_chat_section(self, lost_messages):
        self.function_agent_STM.initiate_chat(
            self,
            message=f"Conversation Section to Summarize:\n{lost_messages}\n\n Please make a function call to append_to_short_term_memory and pass in the key points you can extract from the above conversation section. Do not use 'User' or 'Assistant' - replace 'User' with {self.parent_agent.sender_agent.name}, and replace 'Assistant' with 'I'."
        )      
    
    # Return the full long term memory in list form
    def read_long_term_memory(self):
        with open(self.parent_agent.long_term_memory_path, 'r') as f:
            mems =  f.readlines()
     
        if len(mems) == 0:
            return []
        
        else:
            return mems[0].split('|')       
            
    # Trim off tail of short term memory to incorporate into long (FILO)
    # TODO: Have MMA return a single point summary of the condensed memories to affix to STM as shadow of now missing memories.
    def short_to_long(self):
        # Get the memories in list mode
        mems = self.parent_agent.read_short_term_memory(list_mode = True)
        # Determine trim point using STM Compression Ratio
        trim_num = int(len(mems)*self.parent_agent.DEFAULT_COMPRESSION_RATIO_STM)
        # Split between mems to leave (stay in STM) and mems to store (into LTM)
        mems_to_leave = mems[trim_num:]
        mems_to_store = mems[:trim_num]
        # Rewrite STM with shortened memory list
        self.parent_agent.rewrite_short_term_memory(mems_to_leave)
        
        # Call incorporate_memories, return result.
        return self.incorporate_memories(mems_to_store)
        
    # Present MMA with full LTM, trimmed of STM, and have it redo LTM to incorporate STM
    # TODO: Tune prompt/function defs to ensure smart compression
    # TODO: Return STM shadow
    def incorporate_memories(self, memories):
        self.function_agent_LTM.initiate_chat(
            self,
            message=f"Full Long Term Memory:\n{self.read_long_term_memory()}\n\nNew memory or memories to incorporate:\n{'|'.join(memories)} \n\n Please make a function call to rewrite_memory and pass in the reconfigured long term memory which incorporates the old with the new. It is better to modify memories in place to capture new information instead of always making the memory longer; only make it longer if necessary, but otherwise do your best to condense, reorganize, and rewrite. The goal is for the Long Term Memory you are writing to be as entity dense as possible."
        )
        return True
    
    # Rewrite entire LTM, from list, with formatting
    def rewrite_memory(self, memories):
        memory_list = memories.split('|')
        with open(self.parent_agent.long_term_memory_path, 'w') as f:
            for memory in memory_list:
                f.write(f"{memory}|")
                
        return True       
    
    # Called by MEA - request for information from LTM relating to hint.
    # TODO: improve hint response
    def lookup_from_long(self, hint):
        self.function_agent_LTM.initiate_chat(
            self,
            message=f"Full Long Term Memory:\n{self.read_long_term_memory()}\n\nWhat do I know about: {hint}?\n\n Respond in chat - Do not make a function call. Replace 'you' with {self.parent_agent.sender_agent.name}. End with TERMINATE."
        )
        # Send back the response to the conversing agent. Due to current flow and manual exiting, '-3' is magic number that gets original MMA response to question.
        return self.chat_messages[self.function_agent_LTM][-1]



