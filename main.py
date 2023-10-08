from EnhancedAgents import MemoryEnabledAgent
import autogen

#---------- llm model info --------------
llm_model = 'gpt-3.5-turbo'#'gpt-3.5-turbo' 'gpt-4-0613'

config_list = [
    {
        'model': llm_model,
        'api_key': 'YOUR_API_KEY_HERE',
    }  # OpenAI API endpoint for gpt-3.5-turbo
 
]

llm_config = {"config_list": config_list, "seed": 42}

gpt_config = {
    "seed": 42,  # change the seed for different trials
    "temperature": 0,
    "config_list": config_list,
    "request_timeout": 120,
}

# Make the MemoryEnabledAgent
mem_agent = MemoryEnabledAgent("Cortana", gpt_config)

# Make a user proxy - retrieve mem_agent function map.
user_proxy = autogen.UserProxyAgent(
    name="Andy",
    human_input_mode="ALWAYS",
    max_consecutive_auto_reply=10,
    code_execution_config={"work_dir": "_test"},
    function_map=mem_agent.get_function_map(),
)



# Chat with the Agent
user_proxy.initiate_chat(
    mem_agent,
    message="""(User:{user_name} Connected)""".format(user_name = user_proxy.name)
)
