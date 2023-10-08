# AutoGen_EnhancedAgents
This repository holds enhanced Agents, built for the Microsoft AutoGen Framework. Debuting with a MemoryEnabledAgent with improvements in context/token control, portability, and Plug-and-Play functionality. 


# Table of Contents  
[MemoryEnabledAgent](#MEA)
 - [Overview](#MEA_Overview)
 - [How it Works](#MEA_HowItWorks)
   - [Storing, Shifting, and Summarizing Memories](#MEA_SSSM)


<a name="MEA"/>

# MemoryEnabledAgent 


The Memory Enabled Agent (MEA) inherits from the [AutoGen](ms autogen link here) AssistantAgent class, with changes and features that endow the agent with a persistant, autonomous, and token-stable method of conversation, memory storage, and memory retrieval. This work is inspired by, and extends from, lessons and experiences from developing [AutoGen_MemoryManager](link me) and [AutoGen_IterativeCoding](link me), as well as discussions within the AutoGen community. This work represents a continuation in the efforts to develop a more generally-powerful AI Agent. Feedback and Collaboration is strongly welcomed and encouraged.

<a name="MEA_Overview"/>

## Overview


The MEA was designed to provide an easy-to-implement option for using an Agent with dynamic and self-arranged memory within the AutoGen framework. The implemented system was inspired by literature on human memory systems, and as such includes a Working Memory (CC, Chat-Context), Short-Term Memory (STM, via exChat-Context), and a Long-Term Memory (LTM, via exSTM-Context). The STM stays affixed to the top of the CC and is excluded from FILO concerns. The CC is a fixed number of messages which, when exceeded, uses a compression ratio (CR_1) to remove some of the oldest messages (FILO) and have them be summarized into the STM. The STM also has a fixed number of memories which, when exceeded, uses a CR (CR_2) to remove some of the oldest memories and integrate them into the LTM. Both summary events are executed by the internal MemoryEnabledAgent_Manager, referred to as the Memory Manager Agent, or MMA.

<a name="MEA_HowItWorks"/>

## How it Works

[Diagram Here]

<a name="MEA_SSSM"/>

### Storing, Shifting, and Summarizing Memories

*********************

#### Chat Context

The Chat-Context (CC) exceeding the limit is what drives all memory storage related functions. When the CC exceeds the limit, a Compression Ratio (CR) is applied onto the messages such that:

```python
trim_index = len(messages)*CompressionRatio
lost_messages = messages[:trim_index]
remaining_messages = messages[trim_index:]
```

The trim index splits the chat history per the ratio, with the oldest section (lost_messages) being sent to the Memory Manager Agent (MMA) for processing and appending to the Short-Term Memory (STM), with the newest section (remaining_messages) remaining as the new CC.

The MMA, when presented with the chat section, is prompted:

> Conversation Section to Summarize:\n{lost_messages}\n\n Please make a function call to append_to_short_term_memory and pass in the key points you can extract from the above conversation section.

The MMA will then call `append_to_short_term_memory` and pass in a list of memories meant to capture and significance from the lost_messages.

***************

#### Short-Term Memory

The STM behaves in a similar fashion to the CC, in that it has a limit which,




# ToDo To Make Efficient

- Better prompts for better factoid generation/storage. Sometimes it still does sentences or other copy/paste.
- Automation of CC, STM, and LTM function calls, after ensuring minimal/zero waste.
- Code TODOs.

# ToDo To Make Better

- Create a self reflection cycle to allow memory compression/reformating outside of CC driven demands. Make it accessible to the MEA.
- Create a context-switch cycle, to allow the STM to be reformated from CC/STM/LTM such that it is best prepared for the next task.
- Create a system to allow MEA to adjust STM and LTM-lookup for specific agent - either through more files or better control of entity names in STM and LTM entries.
- Devise a methodology and rationale for splitting LTM into related sections, to allow a larger total LTM but with less cost per LTM lookup if in a properly related section.
- Test and refine methods to achieve optimal performance and efficiency when using the agent in other activities outside of user chat (coding groups, media creation, cross-group ideation, etc...)















## Features

- Memory-Enabled Assistant (MEA) capable of maintaining short-term and long-term memory.
- Memory Manager for summarizing conversation sections and incorporating information into long-term memory.
- Functions for looking up information in long-term memory.
- Smart memory compression to manage memory limits.
- Designed for integration with OpenAI's GPT-3 or similar language models.

## Getting Started

### Prerequisites

- Python 3.10.9
- Libraries mentioned in the code, including Autogen (if not already installed).

### Installation

1. Clone this repository to your local machine:

   ```bash
   git clone https://github.com/your-username/memory-enabled-assistant.git
   ```

2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

### Usage

To use the Memory-Enabled Assistant and Memory Manager, follow these steps:

1. Instantiate the `MemoryEnabledAgent` class to create a Memory-Enabled Assistant.
2. Interact with the assistant by sending and receiving messages.
3. The Memory Manager will automatically handle memory compression and storage when needed.

Here's an example of how to use it:

```python
from autogen import AssistantAgent
from your_module import MemoryEnabledAgent

# Create a Memory-Enabled Assistant
mea = MemoryEnabledAgent(name="MyAssistant", gpt_config=gpt_configuration)

# Send and receive messages with the assistant
mea.receive("Hello, assistant!", sender=user_agent)

# The Memory Manager will manage memories behind the scenes.
```

### Memory Management

- The Memory Manager automatically compresses short-term memory when it exceeds the limit.
- Memories are stored in the `Managed_Memories` directory.
- You can access long-term memories using the `lookup_from_long_term_memory` function.

### Configuration

You can customize memory-related parameters in the code, such as short-term memory limits and compression ratios, to suit your specific needs.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- This code is inspired by the concept of memory-enabled AI agents.
- Thanks to the Autogen library for providing essential tools for AI agent development.
