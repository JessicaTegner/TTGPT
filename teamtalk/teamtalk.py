"""PyTeamTalk

A wrapper around the TeamTalk 5 TCP API.

author: Carter Temm
license: MIT
http://github.com/cartertemm/pyteamtalk
"""


import shlex
import time
import threading
import telnetlib
import warnings
import functools


# constants
## MSG Types
NONE_MSG = 0
USER_MSG = 1
CHANNEL_MSG = 2
BROADCAST_MSG = 3
CUSTOM_MSG = 4

## User Types (from library/teamtalk_lib/teamtalk/common.h)
USERTYPE_NONE	 = 0x00
USERTYPE_DEFAULT      = 0x01
USERTYPE_ADMIN	= 0x02

## Command Errors

CMD_ERR_IGNORE = -1
CMD_ERR_SUCCESS = 0  #indicates success
CMD_ERR_SYNTAX_ERROR = 1000
CMD_ERR_UNKNOWN_COMMAND = 1001
CMD_ERR_MISSING_PARAMETER = 1002
CMD_ERR_INCOMPATIBLE_PROTOCOLS = 1003
CMD_ERR_UNKNOWN_AUDIOCODEC = 1004
CMD_ERR_INVALID_USERNAME = 1005
# command errors due to rights
CMD_ERR_INCORRECT_CHANNEL_PASSWORD = 2001
CMD_ERR_INVALID_ACCOUNT = 2002
CMD_ERR_MAX_SERVER_USERS_EXCEEDED = 2003
CMD_ERR_MAX_CHANNEL_USERS_EXCEEDED = 2004
CMD_ERR_SERVER_BANNED = 2005
CMD_ERR_NOT_AUTHORIZED = 2006
CMD_ERR_MAX_DISKUSAGE_EXCEEDED = 2008
CMD_ERR_INCORRECT_OP_PASSWORD = 2010
CMD_ERR_AUDIOCODEC_BITRATE_LIMIT_EXCEEDED = 2011
CMD_ERR_MAX_LOGINS_PER_IPADDRESS_EXCEEDED = 2012
CMD_ERR_MAX_CHANNELS_EXCEEDED = 2013
CMD_ERR_COMMAND_FLOOD = 2014
CMD_ERR_CHANNEL_BANNED = 2015
# command errors due to invalid state
CMD_ERR_NOT_LOGGEDIN = 3000
CMD_ERR_ALREADY_LOGGEDIN = 3001
CMD_ERR_NOT_IN_CHANNEL = 3002
CMD_ERR_ALREADY_IN_CHANNEL = 3003
CMD_ERR_CHANNEL_ALREADY_EXISTS = 3004
CMD_ERR_CHANNEL_NOT_FOUND = 3005
CMD_ERR_USER_NOT_FOUND = 3006
CMD_ERR_BAN_NOT_FOUND = 3007
CMD_ERR_FILETRANSFER_NOT_FOUND = 3008
CMD_ERR_OPENFILE_FAILED = 3009
CMD_ERR_ACCOUNT_NOT_FOUND = 3010
CMD_ERR_FILE_NOT_FOUND = 3011
CMD_ERR_FILE_ALREADY_EXISTS = 3012
CMD_ERR_FILESHARING_DISABLED = 3013
CMD_ERR_CHANNEL_HAS_USERS = 3015
CMD_ERR_LOGINSERVICE_UNAVAILABLE = 3016

## User rights (from library/teamTalkLib/teamtalk/common.h)
USERRIGHT_NONE = 0x00000000
USERRIGHT_MULTI_LOGIN = 0x00000001
USERRIGHT_VIEW_ALL_USERS = 0x00000002
USERRIGHT_CREATE_TEMPORARY_CHANNEL = 0x00000004
USERRIGHT_MODIFY_CHANNELS = 0x00000008
USERRIGHT_TEXTMESSAGE_BROADCAST = 0x00000010
USERRIGHT_KICK_USERS = 0x00000020
USERRIGHT_BAN_USERS = 0x00000040
USERRIGHT_MOVE_USERS = 0x00000080
USERRIGHT_OPERATOR_ENABLE = 0x00000100
USERRIGHT_UPLOAD_FILES = 0x00000200
USERRIGHT_DOWNLOAD_FILES = 0x00000400
USERRIGHT_UPDATE_SERVERPROPERTIES = 0x00000800
USERRIGHT_TRANSMIT_VOICE = 0x00001000
USERRIGHT_TRANSMIT_VIDEOCAPTURE = 0x00002000
USERRIGHT_TRANSMIT_DESKTOP = 0x00004000
USERRIGHT_TRANSMIT_DESKTOPINPUT = 0x00008000
USERRIGHT_TRANSMIT_MEDIAFILE_AUDIO = 0x00010000
USERRIGHT_TRANSMIT_MEDIAFILE_VIDEO = 0x00020000
USERRIGHT_TRANSMIT_MEDIAFILE = (
	USERRIGHT_TRANSMIT_MEDIAFILE_AUDIO | USERRIGHT_TRANSMIT_MEDIAFILE_VIDEO
)
USERRIGHT_LOCKED_NICKNAME = 0x00040000
USERRIGHT_LOCKED_STATUS = 0x00080000
USERRIGHT_RECORD_VOICE = 0x00100000
USERRIGHT_DEFAULT = (
	USERRIGHT_MULTI_LOGIN
	| USERRIGHT_VIEW_ALL_USERS
	| USERRIGHT_CREATE_TEMPORARY_CHANNEL
	| USERRIGHT_UPLOAD_FILES
	| USERRIGHT_DOWNLOAD_FILES
	| USERRIGHT_TRANSMIT_VOICE
	| USERRIGHT_TRANSMIT_VIDEOCAPTURE
	| USERRIGHT_TRANSMIT_DESKTOP
	| USERRIGHT_TRANSMIT_DESKTOPINPUT
	| USERRIGHT_TRANSMIT_MEDIAFILE
)
USERRIGHT_ALL = 0x0013FFFF
USERRIGHT_KNOWN_MASK = 0x001FFFFF

## Server Subscriptions (from library/teamTalkLib/teamtalk/common.h)
SUBSCRIBE_NONE  = 0x00000000
SUBSCRIBE_USER_MSG	  = 0x00000001
SUBSCRIBE_CHANNEL_MSG   = 0x00000002
SUBSCRIBE_BROADCAST_MSG = 0x00000004
SUBSCRIBE_CUSTOM_MSG = 0x00000008
SUBSCRIBE_VOICE = 0x00000010
SUBSCRIBE_VIDEOCAPTURE = 0x00000020
SUBSCRIBE_DESKTOP = 0x00000040
SUBSCRIBE_DESKTOPINPUT = 0x00000080
SUBSCRIBE_MEDIAFILE = 0x00000100
SUBSCRIBE_ALL = 0x000001FF
SUBSCRIBE_LOCAL_DEFAULT = (SUBSCRIBE_USER_MSG |
	SUBSCRIBE_CHANNEL_MSG |
	SUBSCRIBE_BROADCAST_MSG |
	SUBSCRIBE_CUSTOM_MSG |
	SUBSCRIBE_MEDIAFILE)
SUBSCRIBE_PEER_DEFAULT = (SUBSCRIBE_ALL & ~SUBSCRIBE_DESKTOPINPUT)
SUBSCRIBE_INTERCEPT_USER_MSG = 0x00010000
SUBSCRIBE_INTERCEPT_CHANNEL_MSG = 0x00020000
# SUBSCRIBE_INTERCEPT_BROADCAST_MSG	 = 0x00040000
SUBSCRIBE_INTERCEPT_CUSTOM_MSG  = 0x00080000
SUBSCRIBE_INTERCEPT_VOICE	   = 0x00100000
SUBSCRIBE_INTERCEPT_VIDEOCAPTURE= 0x00200000
SUBSCRIBE_INTERCEPT_DESKTOP	 = 0x00400000
# SUBSCRIBE_INTERCEPT_DESKTOPINPUT	  = 0x00800000
SUBSCRIBE_INTERCEPT_MEDIAFILE = 0x01000000
SUBSCRIBE_INTERCEPT_ALL = 0x017B0000


def split_parts(msg):
	"""Splits a key=value pair into a tuple."""
	index = msg.find("=")
	return (msg[:index], msg[index+1:])


def split_quoted(message):
	"""Like shlex.split, but preserves quotes."""
	pos = -1
	inquote = False
	buffer = ""
	final = []
	while pos < len(message)-1:
		pos += 1
		token = message[pos]
		if token == " " and not inquote:
			final.append(buffer)
			buffer = ""
			continue
		if token == "\"" and message[pos-1] != "\\":
			inquote = not inquote
		buffer += token
	final.append(buffer)
	return final


def parse_tt_message(message):
	"""Parses a message sent by Teamtalk.
	Also preserves datatypes.
	Returns a tuple of (event, parameters)"""
	params = {}
	message = message.strip()
	message = split_quoted(message)
	event = message[0]
	message.remove(event)
	for item in message:
		k, v = split_parts(item)
		# Lists take the form [x,y,z]
		if v.startswith("[") and v.endswith("]"):
			v = v.strip("[]")
			# Make sure we aren't dealing with a blank list
			if v:
				v = v.split(",")
				lst = []
				for val in v:
					if val.isdigit():
						lst.append(int(val))
					# I've never once seem values take a form other than int
					# better to assume it is possible, however
					else:
						lst.append(val)
				v = lst
			else:
				v = []
		# preserve ints
		elif v.isdigit():
			v = int(v)
		# strings
		elif v.startswith('"') and v.endswith('"'):
			v = v[1:-1]
		params[k] = v
	return event, params


def build_tt_message(event, params):
	"""Given an event and dictionary containing parameters, builds a TeamTalk message.
	Also preserves datatypes.
	inverse of parse_tt_message"""
	message = event
	for key, val in params.items():
		message += " " + key + "="
		# integers aren't encapsulated in quotes
		if isinstance(val, int) or isinstance(val, str) and val.isdigit():
			message += str(val)
		# nor are lists
		elif isinstance(val, list):
			message += "["
			for v in val:
				if isinstance(v, int) or isinstance(v, str) and v.isdigit():
					message += str(v) + ","
				else:
					message += '"' + v + '",'
			# get rid of the trailing ",", if necessary
			if len(val) > 0:
				message = message[:-1]
			message += "]"
		else:
			message += '"' + val + '"'
	return message


class TeamTalkError(Exception):
	"""Raised on an error event from the server"""
	def __init__(self, code, message):
		self.code = code
		self.message = message

	def __str__(self):
		return "[" + self.code + "]: " + self.message


class TeamTalkServer:
	"""Represents a single TeamTalk server."""

	def __init__(self, host=None, tcpport=10333):
		self.set_connection_info(host, tcpport)
		self.con = None
		self.pinger_thread = None
		self.message_thread = None
		self.disconnecting = False
		self.logging_in = False
		self.logged_out = False
		self.current_id = 0
		self.last_id = 0
		self.subscriptions = {}
		self.channels = []
		self.users = []
		self.me = {}
		self.server_params = {}
		self.files = []
		self._subscribe_to_internal_events()
		self._login_sequence = 0


	def set_connection_info(self, host, tcpport=10333):
		"""Sets the server's host and TCP port"""
		self.host = host
		self.tcpport = tcpport

	def connect(self):
		"""Initiates the connection to this server
		Raises an exception on failure"""
		self.con = telnetlib.Telnet(self.host, self.tcpport)
		# the first thing we should get is a welcome message
		welcome = self.read_line(timeout=3)
		if not welcome:
			raise TimeoutError("Server failed to send welcome message in time")
		welcome = welcome.decode()
		event, params = parse_tt_message(welcome)
		if event != "teamtalk":
			# error
			# could mean we're working with a TT 4 server, or different protocol entirely
			return
		self.server_params = params

	def login(self, nickname, username, password, client, protocol="5.6", version="1.0", callback=None):
		"""Attempts to log in to the server.
		This should be called immediately after connect to prevent timing out.
		Blocks until the login sequence has completed.
		If callback is specified, it behaves the same as handle_messages for the duration of this sequence.
		To intersept failed logins, provide a callback and check for the "error" event.
		"""
		message = build_tt_message(
			"login",
			{
				"nickname": nickname,
				"username": username,
				"password": password,
				"clientname": client,
				"protocol": protocol,
				"version": version,
				"id": 1,
			},
		)
		self.send(message)
		self.start_threads()
		self._login_sequence = 1
		self.handle_messages(callback=callback)

	def start_threads(self):
		self.pinger_thread = threading.Thread(target=self.handle_pings)
		self.pinger_thread.daemon = True
		self.pinger_thread.start()

	def read_line(self, timeout=None):
		"""Reads and returns a line from the server"""
		if self.disconnecting:
			return False
		return self.con.read_until(b"\r\n", timeout)

	def send(self, line):
		"""Sends a line to the server"""
		if self.disconnecting:
			return False
		if isinstance(line, str):
			line = line.encode()
		line = line.replace(b"\n", b"\r")
		if not line.endswith(b"\r\n"):
			line += b"\r\n"
		self.con.write(line)

	def disconnect(self):
		"""Disconnect from this server.
		Signals all threads to stop"""
		self.disconnecting = True
		self.con.close()

	def handle_messages(self, timeout=1, callback=None):
		"""Processes all incoming messages
		If callback is specified, it will be ran every time a new line is received from the server (or timeout seconds) along with an instance of this class, the event name, and parameters.
		Please note: If timeout is None (or unspecified), the callback function may take a while to execute in instances when we aren't getting packets. This behavior may not be desireable for many applications.
			If in doubt, set a timeout.
			Also be wary of extremely small timeouts when handling larger lines
		"""
		while not self.disconnecting:
			if self._login_sequence == 2:
				self._login_sequence = 0
				break
			line = self.read_line(timeout)
			line = line.strip()
			if line == b"pong":
				# response to ping, which is handled internally
				# we don't actually care about getting something back, we just send them to make the server happy
				line = b"" # drop it
			try:
				line = line.decode()
			except UnicodeDecodeError:
				print("failed to decode line: " + line)
				if callable(callback):
					callback(self, "", {})
				continue
			if not line:
				if callable(callback):
					callback(self, "", {})
				continue # nothing to do
			event, params = parse_tt_message(line)
			event = event.lower()
			if event == "error":
				# indicates success or irrelevance
				if params["number"] == CMD_ERR_IGNORE or params["number"] == CMD_ERR_SUCCESS:
					continue
				raise TeamTalkError(params["number"], params["message"])
			# Call messages for the event if necessary
			for func in self.subscriptions.get(event, []):
				func(self, params)
			# finally, call the callback
			if callable(callback):
				callback(self, event, params)


	def _sleep(self, seconds):
		"""Like time.sleep, but immediately halts execution if we need to disconnect from a server"""
		starttime = time.time()
		while not self.disconnecting and time.time() - starttime <= seconds:
			time.sleep(0.005)

	def handle_pings(self):
		"""Handles pinging the server at a reasonable interval.
		Intervals are calculated based on the server's usertimeout value.
		This function always runs in it's own thread."""
		pingtime = 0
		while not self.disconnecting:
			self.send("ping")
			# in case usertimeout was changed somehow
			# logic from TTCom, which had a preferable approach to TT clients for what we're doing
			# better safe than sorry
			pingtime = float(self.server_params["usertimeout"])
			if pingtime < 1:
				pingtime = 0.3
			elif pingtime < 1.5:
				pingtime = 0.5
			else:
				pingtime *= 0.75
			self._sleep(pingtime)

	def subscribe(self, event, func=None):
		"""Starts calling func every time event is encountered, passing along a copy of this class as well as the parameters from the TT message
		This can also be used as a decorator
		"""

		def wrapper(_func):
			evt = event.lower()
			subs = self.subscriptions.get(evt)
			# events are added as we subscribe to them
			if subs:
				self.subscriptions[evt].append(_func)
			else:
				self.subscriptions[evt] = [_func]
			return _func

		if func:
			return wrapper(func)
		else:
			return wrapper

	def unsubscribe(self, event, func):
		"""Stops calling func when event is encountered
		Raises a KeyError or ValueError on failure"""
		event = event.lower()
		self.subscriptions[event].remove(func)

	def _subscribe_to_internal_events(self):
		"""Subscribes to all internal events that keep track of the server's state.
			self.users, self.me, self.channels, self.server_params, etc.
		Called automatically
		"""
		funcs = [i for i in dir(self) if i.startswith("_handle_")]
		for func in funcs:
			event = func.replace("_handle_", "")
			func = getattr(self, func)
			if callable(func):
				self.subscribe(event, func)

	def get_channel(self, id, index=False):
		"""Retrieves attributes for channels with the requested id.
		If index is False, returns a dict. Otherwise, returns the channel's index in self.channels
		If id is of type str, look for matching names
		If id is an int, look for matching chanid's
		If id is a dict, we assume params are lazily being passed and try searching for a chanid"""
		if isinstance(id, dict):
			id = id.get("chanid")
			if not id:
				return
		found = False
		for i, channel in enumerate(self.channels):
			if isinstance(id, int) and channel["chanid"] == id:
				found = True
			elif isinstance(id, str) and channel["channel"] == id:
				found = True
			if found:
				if index:
					return i
				else:
					return channel

	def get_user(self, id, index=False):
		"""Retrieves attributes for users with the requested id.
		If index is False, returns a dict. Otherwise, returns the user's index in self.users
		If id is of type str, look for matching nicknames
			Be careful, though, as teamtalk imposes no limit on users with identical nicknames.
		If id is an int, look for matching userids
		If id is a dict, we assume params are lazily being passed and try searching for a userid
		"""
		if isinstance(id, dict):
			id = id.get("userid")
			if not id:
				return
		found = False
		for i, user in enumerate(self.users):
			if isinstance(id, int) and user["userid"] == id:
				found = True
			elif isinstance(id, str) and user["nickname"] == id:
				found = True
			if found:
				if index:
					return i
				else:
					return user

	def get_file(self, id, channel=None, index=False):
		"""Retrieves attributes for files with the requested id.
		If channel is given, limit the search to only files in the specified channel, can be anything accepted by get_channel
		If index is False, returns a dict. Otherwise, returns the file's index in self.files
		If id is of type str, look for matching filenames
			Be careful, though, as teamtalk imposes no limit on files with the same name in different channels.
		If id is an int, look for matching fileids
		If id is a dict, we assume params are lazily being passed and try searching for a fileid"""
		if isinstance(id, dict):
			id = id.get("fileid")
			if not id:
				return
		channel = self.get_channel(channel)
		channel = channel.get("chanid")
		found = False
		for i, file in enumerate(self.files):
			if isinstance(id, int) and file["fileid"] == id:
				if channel and file["chanid"] == channel:
					found = True
			elif isinstance(id, str) and file["filename"] == id:
				if channel and file["chanid"] == channel:
					found = True
			if found:
				if index:
					return i
				else:
					return file

	def get_users_in_channel(self, id=None):
		"""Retrieves a list of users in the specified channel.
		id can be anything accepted by get_channel
		There is one exception, however. If None, looks for users that aren't said to be in any channel"""
		users = []
		if id:
			channel = self.get_channel(id)
			id = channel.get("chanid")
		for user in self.users:
			if user.get("chanid") == id:
				users.append(user)
		return users

	def get_role(self, user=None):
		"""Returns an str representing the provided user's role.
		User can be anything accepted by get_user
			If None, returns our role instead
		Possible values are "default", "admin" and "none"
		"""
		if user:
			user = self.get_user(user)
			usertype = user.get("usertype")
		else:
			usertype = self.me.get("usertype")
		if usertype == USERTYPE_DEFAULT:
			return "default"
		elif usertype == USERTYPE_ADMIN:
			return "admin"
		else:
			return "none"

	# helpers for common actions

	def join(self, channel, password="", id=None):
		"""Joins the specified channel, optionally with a password.
		channel can be anything accepted by get_channel
		An "error" event is thrown on failure, "joined" on success"""
		channel = self.get_channel(channel)
		chanid = channel["chanid"]
		params = {"chanid": chanid, "password": password}
		if id:
			params["id"] = id
		msg = build_tt_message("join", params)
		self.send(msg)

	def leave(self, id=None):
		"""Leaves the current channel.
		An "error" event is thrown on failure, "left" on success"""
		params = {}
		if id:
			params["id"] = id
		msg = build_tt_message("leave", params)
		self.send(msg)

	def kick(self, target, channel=None, id=None):
		"""Kicks the provided user from a channel (if specified) otherwise the server.
		Target can be anything accepted by get_user
		Channel can be anything accepted by get_channel"""
		target = self.get_user(target)
		target = target.get("userid")
		params = {"userid": target}
		if channel:
			channel = self.get_channel(channel)
			channel = channel.get("chanid")
			params["chanid"] = channel
		if id:
			params["id"] = id
		msg = build_tt_message("kick", params)
		self.send(msg)

	def move(self, user, destination, id=None):
		"""Moves the provided user to destination.
		User can be anything accepted by get_user
		Destination can be anything accepted by get_channel"""
		user = self.get_user(user)
		user = user.get("userid")
		channel = self.get_channel(destination)
		channel = channel.get("chanid")
		params = {"userid": user, "chanid": channel}
		if id:
			params["id"] = id
		msg = build_tt_message("moveuser", params)
		self.send(msg)

	def change_status(self, statusmode, statusmsg, id=None):
		"""
		Changes the status for the current user
		status modes are as follows:
		0 Online
		1 Away
		2 Question
		"""
		params = {"statusmode": statusmode, "statusmsg" : statusmsg}
		if id:
			params["id"] = id
		msg = build_tt_message("changestatus", params)
		self.send(msg)

	def change_nickname(self, nickname, id=None):
		"""Changes the nickname for the current user."""
		params = {"nickname": nickname}
		if id:
			params["id"] = id
		msg = build_tt_message("changenick", params)
		self.send(msg)

	def user_message(self, to, content, id=None):
		"""Sends a private message to a user on this server.
		To is the recipient, and can be anything accepted by get_user
		Content is the text that will be sent"""
		to = self.get_user(to)
		to = to.get("userid")
		params = {"type": USER_MSG, "content": content, "destuserid": to}
		if id:
			params["id"] = id
		msg = build_tt_message("message", params)
		self.send(msg)

	def channel_message(self, content, to=None, id=None):
		"""Sends a channel message.
		Content is the text that will be sent
		To can be None (current channel) or anything accepted by get_channel
			Note that only admins are able to send messages to channels without joining first.
		"""
		if to:
			to = self.get_channel(to)
			to = to.get("chanid")
		else:
			to = self.me.get("chanid")
		params = {"type": CHANNEL_MSG, "content": content, "chanid": to}
		if id:
			params["id"] = id
		msg = build_tt_message("message", params)
		self.send(msg)

	def broadcast_message(self, content, id=None):
		"""Sends a broadcast (serverwide) message.
		Content is the text that will be sent"""
		params = {"type": BROADCAST_MSG, "content": content}
		if id:
			params["id"] = id
		msg = build_tt_message("message", params)
		self.send(msg)

	def remove_channel(self, channel, id=None):
		"""Removes a channel from the server, only available to admins.
		channel can be anything accepted by get_channel"""
		channel = self.get_channel(channel)
		chanid = channel.get("chanid")
		params = {"chanid": chanid}
		if id:
			params["id"] = id
		msg = build_tt_message("removechannel", params)
		self.send(msg)

	def channel_operator(self, user=None, channel=None, password="", op=True, id=None):
		"""Grants operator privileges on the provided channel.
		user can be None (current user) or anything accepted by get_user
		password is the operator password
		channel can be None (current channel) or anything accepted by get_channel
		if op is False, permission is revoked"""
		op = int(op)
		if channel:
			channel = self.get_channel(channel)
			channel = channel.get("chanid")
		else:
			channel = self.me.get("chanid")
		if user:
			user = self.get_user(user)
			user = user.get("userid")
		else:
			user = self.me.get("userid")
		params = {"chanid": channel, "userid": user, "opstatus": op}
		if id:
			params["id"] = id
		msg = build_tt_message("op", params)
		self.send(msg)

	def subscribe_to(self, user, subscription, id=None):
		"""Subscribe to an event on this server for a given user.
			Not to be confused with subscribe, which maps events to local functions.
		user can be anything accepted by get_user
		subscription can be any teamtalk.SUBSCRIBE_* constant, or a bitmask for multiple"""
		user = self.get_user(user)
		user = user.get("userid")
		params = {"userid": user, "sublocal": subscription}
		if id:
			params["id"] = id
		msg = build_tt_message("subscribe", params)
		self.send(msg)

	def unsubscribe_from(self, user, subscription, id=None):
		"""Unsubscribes from an event on this server for a given user.
			Not to be confused with subscribe, which maps events to local functions.
		user can be anything accepted by get_user
		subscription can be any teamtalk.SUBSCRIBE_* constant, or a bitmask for multiple"""
		user = self.get_user(user)
		user = user.get("userid")
		params = {"userid": user, "sublocal": subscription}
		if id:
			params["id"] = id
		msg = build_tt_message("unsubscribe", params)
		self.send(msg)


	# Internal event responses
	# We subscribe to these to ensure we have the latest info
	# These take precedence over custom responses
	# methods are static because instances of this class are sent along to every response already, adding self would
	# be a redundancy

	@staticmethod
	def _handle_error(self, params):
		"""Event fired when something goes wrong.
		params["number"] contains the code, and params["message"] is a human-friendly explanation of what went wrong"""
		print(f"error ({params['number']}): {params['message']}")

	@staticmethod
	def _handle_begin(self, params):
		"""Event fired to acknowledge the start of an ordered response.
		When a sent message contains the field "id=*", responses take the form:
			begin id=*
			contents
			end id=*
		Messages are sent this way when ordering needs to be preserved.
		"""
		self.current_id = params["id"]
		# Logging in sends a flood of "loggedin" and "addchannel" packets
		# Handle these differently
		if self.current_id == 1:
			self.logging_in = True

	@staticmethod
	def _handle_end(self, params):
		"""Event fired to acknowledge the end of an ordered response.
		When a sent message contains the field "id=*", responses take the form:
			begin id=*
			contents
			end id=*
		Messages are sent this way when ordering needs to be preserved.
		"""
		self.current_id = 0
		# Logging in sends a flood of "loggedin" and "addchannel" packets
		# Make it so these events can be handled differently if necessary
		if params["id"] == 1:
			self.logging_in = False
			self._login_sequence = 2

	@staticmethod
	def _handle_loggedin(self, params):
		"""Event fired when a user has just logged in.
		Is also sent during login for every currently logged in user"""
		user_index = self.get_user(params["userid"], index=True)
		if not user_index:
			self.users.append(params)
		else:
			# something was updated
			# I don't think this should happen, but just to be sure
			self.users[user_index].update(params)

	@staticmethod
	def _handle_loggedout(self, params):
		"""Event fired when a user logs out"""
		if not params.get("userid") or params["userid"] == self.me["userid"]:
			self.logged_out = True
			self.disconnect()
		else:
			user = self.get_user(params["userid"])
			if user:
				self.users.remove(user)

	@staticmethod
	def _handle_accepted(self, params):
		"""Event fired immediately after an accepted login.
		Contains information about the current user"""
		self.me.update(params)
		self.logged_out = False

	@staticmethod
	def _handle_serverupdate(self, params):
		"""Event fired after login that exposes more info to a client
		May also mean that attributes of this server have changed"""
		self.server_params.update(params)

	@staticmethod
	def _handle_addchannel(self, params):
		"""Event fired when a new channel has been created
		Can also be used to tell a newly connected user about a channel"""
		chan_index = self.get_channel(params["chanid"], index=True)
		if not chan_index:
			self.channels.append(params)
		else:
			# shouldn't happen
			self.channels[chan_index].update(params)

	@staticmethod
	def _handle_updatechannel(self, params):
		"""Event fired when an attribute of a channel has changed"""
		chan_index = self.get_channel(params["chanid"], index=True)
		if chan_index:
			self.channels[chan_index].update(params)

	@staticmethod
	def _handle_removechannel(self, params):
		"""Event fired when a channel is deleted"""
		channel = self.get_channel(params["chanid"])
		if channel:
			self.channels.remove(channel)

	@staticmethod
	def _handle_joined(self, params):
		"""Event fired when this user joins a channel"""
		self.me.update(params)

	@staticmethod
	def _handle_left(self, params):
		"""Event fired when this user leaves a channel"""
		del self.me["chanid"]

	@staticmethod
	def _handle_adduser(self, params):
		"""Event fired when a user is added (manually joins or is moved) to a channel.
		Can also be used to tell a newly connected user about the location of other users on the server"""
		user_index = self.get_user(params["userid"], index=True)
		if user_index != None:
			self.users[user_index].update(params)

	@staticmethod
	def _handle_removeuser(self, params):
		"""Event fired when a user is removed from (or leaves) a channel"""
		user_index = self.get_user(params["userid"], index=True)
		if user_index != None:
			del self.users[user_index]["chanid"]

	@staticmethod
	def _handle_updateuser(self, params):
		"""Event fired when an attribute of a user has changed"""
		user_index = self.get_user(params["userid"], index=True)
		if user_index != None:
			self.users[user_index].update(params)

	@staticmethod
	def _handle_addfile(self, params):
		"""Event fired after a user joins a channel where files are available.
		Sent for every downloadable file."""
		self.files.append(params)

	@staticmethod
	def _handle_removefile(self, params):
		"""Event fired when a file is removed from a channel."""
		file_index = self.get_file(params["filename"], params["chanid"], index=True)
		if file_index != None:
			del self.files[file_index]
