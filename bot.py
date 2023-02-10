from multiprocessing.dummy import Pool
import sys
import json
import hashlib

from revChatGPT.Official import Chatbot
import openai

import teamtalk

def split_string(string):
    chunks = []
    while len(string) > 500:
        end = string[:500].rfind(".")
        if end == -1:
            end = 500
        chunks.append(string[:end+1])
        string = string[end+1:]
    chunks.append(string)
    return chunks

def validate_server_info(server_info):
	if "host" not in server_info:
		raise ValueError("No host specified in server_info.json")
	if "port" not in server_info:
		raise ValueError("No port specified in server_info.json")
	if "nickname" not in server_info:
		raise ValueError("No nickname specified in server_info.json")
	if "username" not in server_info:
		raise ValueError("No username specified in server_info.json")
	if "password" not in server_info:
		raise ValueError("No password specified in server_info.json")
	if "channel_id" not in server_info:
		raise ValueError("No channel specified in server_info.json")
	if "openai_api_key" not in server_info:
		raise ValueError("No openai_api_key specified in server_info.json")

t = teamtalk.TeamTalkServer()
server_info = None
chatbot = None

def handle_commands(content):
	if content[0] == "reset":
		chatbot.reset()
		return "Conversation reset."
	if content[0] == "rollback" and len(content) == 2:
		try:
			chatbot.rollback(int(content[1]))
			return f"Rolled back {content[1]} messages."
		except ValueError:
			return "Invalid number of messages to rollback."
		except IndexError:
			return "Rolled back to the start of the conversation."
	if content[0] == "help":
		return "Available commands:\nreset - Resets the conversation.\nrollback x - Rolls the conversation back by x messages.\nhelp - Shows this message."
	else:
		return ""

def _make_gpt_request(original_content, conversation_id):
	try:
		response = openai.Completion.create(engine="text-davinci-003", prompt=original_content, max_tokens=2000)
		message = response["choices"][0]["text"]
	except Exception as e:
		message = f"Error: {str(e)}"
	# if result is empty or just a newline, return
	if message .strip() == "" or message .strip() == "":
		message  = "I don't know what to say."
	# remove all blank lines
	message  = "\n".join([line for line in message .split("\n") if line.strip() != ""])
	return message

def make_gpt_request(original_content, conversation_id):
	with  Pool(None) as p:
		result = p.apply_async(_make_gpt_request, (original_content, conversation_id))
		while not result.ready():
			pass
	return result.get()


def handle_channel_message(original_content, content, conversation_id):
	cmd_result = handle_commands(content[0:])
	if cmd_result != "":
		return cmd_result
	else:
		return make_gpt_request(original_content, conversation_id)


@t.subscribe("messagedeliver")
def message(server, params):
	if params["srcuserid"] == server.me["userid"]:
		return
	if params["type"] == teamtalk.CHANNEL_MSG:
		conversation_id = str(server_info["host"])+":"+str(params["chanid"])
		conversation_id = hashlib.sha256(conversation_id.encode()).hexdigest()
		original_content = params["content"].strip().split(" ")
		original_content = original_content[1:]
		original_content = " ".join(original_content)
		content = params["content"].strip().lower().split(" ")
		# make sure that content it ast least 2 long
		if len(content) < 2:
			return
		if content[0] != "@gpt":
			return ""
		result = handle_channel_message(original_content, content[1:], conversation_id)
		if not result:
			return
		# split the string into chunks of 500 characters at the nearest full stop
		message  = split_string(result)
		for chunk in message :
			try:
				server.channel_message(chunk)
			except teamtalk.TeamTalkError as e:
				print(chunk)
				print(e)
		chatbot.save_conversation(conversation_id)
		chatbot.conversations.save("conversations.json")
	if params["type"] == teamtalk.USER_MSG:
		conversation_id = str(server_info["host"])+":"+str(params["srcuserid"])
		conversation_id = hashlib.sha256(conversation_id.encode()).hexdigest()
		original_content = params["content"].strip()
		content = params["content"].strip().lower().split(" ")
		# make sure that content it ast least 1 long
		if len(content) < 1:
			return
		result = handle_channel_message(original_content, content, conversation_id)
		if not result:
			return
		# split the string into chunks of 500 characters at the nearest full stop
		message  = split_string(result)
		for chunk in message :
			try:
				server.user_message(params["srcuserid"], chunk)
			except teamtalk.TeamTalkError as e:
				print(chunk)
				print(e)
		chatbot.save_conversation(conversation_id)
		chatbot.conversations.save("conversations.json")

def main(server_info):
	t.set_connection_info(server_info["host"], server_info["port"])
	t.connect()
	t.login(server_info["nickname"], server_info["username"], server_info["password"], "TTGPTClient")
	t.join(t.get_channel(server_info["channel_id"]))
	while True:
		try:
			t.handle_messages(2)
		except teamtalk.TeamTalkError as e:
			print(e.code)
			print(e.message)



if __name__ == "__main__":
	server_info = json.load(open("config.json"))
	validate_server_info(server_info)
	chatbot = Chatbot(server_info["openai_api_key"])
	openai.api_key = server_info["openai_api_key"]
	try:
		chatbot.conversations.load("conversations.json")
	except FileNotFoundError:
			pass
	main(server_info)
