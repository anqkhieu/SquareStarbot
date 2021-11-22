import discord
from discord.ext import commands

import pymongo
from pymongo import MongoClient
import certifi

import asyncio, time, random, json, os
from dotenv import load_dotenv

from square.client import Client
import uuid

# Testing Options
DEBUG = True
load_dotenv()

#################################################################

# Get Credentials
mongoConn = os.getenv('MONGO_CONNECTION_SRV')
discordToken = os.getenv('DISCORD_BOT_TOKEN')

# MongoDB Setup
ca = certifi.where()
cluster = MongoClient(mongoConn)
db = cluster["SquareDemo"]
profiles = db["SquareDemoProfiles"]

# Square Python SDK Setup
square_client = Client(access_token=os.getenv('SQUARE_ACCESS_TOKEN'), environment='sandbox')
loyalty_api = square_client.loyalty
program_result = square_client.loyalty.retrieve_loyalty_program(program_id = "main")
if program_result.is_success(): pointsName = program_result.body['program']['terminology']['other']
else: pointsName = 'Points'

# Discord Bot --------------------------------------------------
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix='!', intents = intents)
client.remove_command('help')

# On Discord Bot Startup
@client.event
async def on_ready():
	print(f'{client.user} has connected to Discord!')
	await client.change_presence(activity=discord.Game(name='Giving out stars! ⭐'))

# Send Welcome Message and Link Square Loyalty Account
@client.event
async def on_member_join(member):
	content = f":wave:  **WELCOME TO THE XYZ COMMUNITY DISCORD!** \
	\n\nThis is the official community server for x/y/z interest or fanclub. This is an example welcome message that can be customized. Follow us on [YouTube channel](https://www.youtube.com/) and check out our [Merch Store](https://squareup.com/us/en)."

	embed = discord.Embed(description=content, colour=discord.Colour.orange())
	await member.send(embed=embed)
	time.sleep(1)
	await RequestLoyaltyAccountLinkage(member)

# Gamify Member Activity, Give EXP for Messages
@client.event
async def on_message(message):
	if message.author == client.user: return
	await client.process_commands(message)

	userKey = {'_id': message.author.id}
	userExists = profiles.count_documents(userKey, limit = 1)

	# Create a database entry for new user
	if not userExists:
		values = {'level': 1, 'exp': 1, 'loyalty_account_id': False, 'loyalty_points': 0}
		profiles.update_one(userKey, {'$set': values}, upsert=True)
		if DEBUG: print(f'User {message.author} does not exist, creating database entry.')
	else:
		# Only Loyalty Program Member Server Earn EXP for Server Messages
		if not isinstance(message.channel, discord.channel.DMChannel):
			try: loyalty_account_id = profiles.find_one({'_id': message.author.id})['loyalty_account_id']
			except:
				print('no loyalty account found')
				return

			if profiles.find_one({'_id': message.author.id})['loyalty_account_id'] != None:
				profiles.update_one(userKey, {'$inc': {'exp':1}}, upsert=True)
				levelNum = CheckLevelUp(profiles.find_one(userKey)['exp'], message.author.id)
				if levelNum:
					congratz_messages = [
					f"Congratz, {message.author.mention}! You are now Level {levelNum}. 🎉",
					f"Woohoo! {message.author.mention} is now Level {levelNum}. 🎊",
					f"Wow, {message.author.mention} has reached Level {levelNum}. 🥳"]
					num = random.randint(1,len(congratz_messages)) - 1
					content = congratz_messages[num] + f' You earned {levelNum * 50} {pointsName}.'
					AddLoyaltyPoints(message.author.id, levelNum * 50, reason=f'Reached Level {levelNum} on Discord!')
					embed = discord.Embed(description=content, colour=discord.Colour(0x6e3277))
					await message.channel.send(embed=embed)


# Gives Daily Reward of Loyalty Points, Incentivizes User Retention
@client.command()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
	num = random.randint(2,5)
	num2 = random.randint(1,3)
	totalPts = num ** num2
	if totalPts < 50: totalPts = 10

	if totalPts > 100: content = f"Holy smokes!! You won {totalPts} {pointsName} in the daily check-in! 🥳"
	elif totalPts >= 50: content = f"Wow, very nice. You won {totalPts} {pointsName} for checking in today. 🎉"
	else: content = f"Thanks for your support! You won {totalPts} {pointsName} for swinging by today. 🎊"

	embed = discord.Embed(description=content, colour=discord.Colour(0x6e3277))
	await ctx.send(embed=embed)
	AddLoyaltyPoints(ctx.message.author.id, totalPts, reason='Daily check-in reward!')

@daily.error
async def daily_error(ctx, error):
	if isinstance(error, commands.CommandOnCooldown):
		waitTime = ConvertSecondsToTime(error.retry_after)
		content = f"⏰ You're on cooldown! You may collect your daily reward again in {waitTime}."
		embed = discord.Embed(description=content, colour=discord.Colour(0x6e3277))
		await ctx.send(embed=embed)
	else:
		raise error

# Link Loyalty Account in DMs
@client.command()
async def link(ctx):
	if not isinstance(ctx.channel, discord.channel.DMChannel):
		title = f":scream:  **ERROR**"
		content = f"You can only use this command in direct messages with this bot for privacy protection."
		embed = discord.Embed(title=title, description=content, colour=discord.Colour.red())
		await ctx.send(embed=embed)
	else:
		await RequestLoyaltyAccountLinkage(ctx.message.author)

# Gift Loyalty Points to Tagged User(s)
@client.command(aliases=['give'])
async def gift(ctx, *args):
	if ctx.message.author.guild_permissions.administrator:
		numPoints = 0
		for arg in args:
			if arg.isdigit(): numPoints = int(arg)
			break
		if numPoints > 0:
			for member in ctx.message.mentions:
				try:
					AddLoyaltyPoints(member.id, numPoints, reason=f'Gifted points by {ctx.message.author.name}.')
					content = f"{member.name} has been gifted {numPoints} {pointsName}! :tada:"
					embed = discord.Embed(description=content, colour=discord.Colour.orange())
					await ctx.send(embed=embed)
				except Exception as e:
					title = f":scream:  **ERROR**"
					content = f"{pointsName.capitalize()} could not be gifted to {member.name}. Please make sure you have a valid loyalty account. Use the `!link` command in direct messages with the bot to create a new loyalty rewards account or connect and existing one. \n\n{e}"
					embed = discord.Embed(title=title, description=content, colour=discord.Colour.red())
					await ctx.send(embed=embed)
	else:
		title = f":scream:  **INADEQUATE PERMISSIONS**"
		content = f"You must have administrator priviledges to gift out {pointsName}."
		embed = discord.Embed(title=title, description=content, colour=discord.Colour.red())
		await ctx.send(embed=embed)

# Shows User's Current Loyalty Point Balance
@client.command(aliases=['mystats', 'balances', 'bal'])
async def profile(ctx):
	userKey = ctx.message.author.id
	exp = profiles.find_one({'_id': userKey})['exp']

	level = GetLevelFromExp(exp)
	next_level_exp = NextLevelFormula(level+1)

	loyalty_account_id = profiles.find_one({'_id': userKey})['loyalty_account_id']
	result = square_client.loyalty.retrieve_loyalty_account(account_id = loyalty_account_id)

	if result.is_success():
		loyalty_account = result.body['loyalty_account']
		content = f"🌟 **{ctx.message.author}** \
					\n\n __Your Stats__\
					\n**Level:** {GetLevelFromExp(exp)} \
					\n**EXP:** {exp} / {next_level_exp} \
					\n\n__Loyalty Program Stats__\
					\n**Current Balance:** {loyalty_account['balance']} {pointsName} \
					\n**Lifetime Earned:** {loyalty_account['lifetime_points']} {pointsName}"
	elif result.is_error():
		print(result.errors)
		content = f"🌟 **{ctx.message.author}** \
					\n __Your Stats__\
					\n**Level:** {level} / {next_level_exp} \
					\n**EXP:** {exp}"
	embed = discord.Embed(description=content, colour=discord.Colour.orange())
	await ctx.send(embed=embed)

# Shows Loyalty Program Rewards
@client.command(aliases=['loyalty'])
async def rewards(ctx):
	result = square_client.loyalty.retrieve_loyalty_program(program_id = "main")

	if result.is_success():
		program = result.body['program']
		amount = '{:.2f}'.format(program['accrual_rules'][0]['spend_amount_money']['amount'] * 0.01)

		title = '🌟  OUR LOYALTY REWARDS PROGRAM'
		content = f"You can earn loyalty points by purchasing merch from our store or by being an active, positive community member! \
			In our program, you earn {program['accrual_rules'][0]['points']} {pointsName} for every {amount} \
			{program['accrual_rules'][0]['spend_amount_money']['currency']} spent. By being a positive community member in \
			this Discord, you can also earn {pointsName}. To get your first {pointsName}, link your phone number to collect points.\
			\n\
			\n**How to earn {pointsName}?**\
			\nBy being a awesome, friendly, and active member in the Discord, by sharing your love with your fanart, or by reporting bugs. \
			To get started, try the `!daily` to get some points for stopping by today!  \
			\n\
			\n\
			🏆 __**Reward Tiers**__\n"

		for reward in program['reward_tiers']:
			content += f"*{reward['points']} {pointsName}* for {reward['name']}\n"

	elif result.is_error():
		content = 'Oh no, there was an error! Contact the staff team. 😬'
		print(result)

	embed = discord.Embed(title=title, description=content, colour=discord.Colour.orange())
	await ctx.send(embed=embed)

# Shows a Short Bot Description
@client.command(aliases=['what'])
async def about(ctx):
	embed = discord.Embed(description="‍🌟  **WHAT IS 'SQUARE STARBOT'?** \
	\n*Everything you need to integrate your Community Discord with your Square Store!* \
	\nGamification. Automation. Convenience. \
	\n\n__**Features**__  \
	\n+ Gamify positive community engagement with Square store loyalty points \
	\n+ Track orders and refunds conveniently in a Discord channel \
	\n+ Distribute loyalty points for events and giveaways to the masses fast \
	\n+ Make it easy for fans to check their loyalty point balances and new rewards \
	\n+ Features a leveling and progression system with customizable rewards \
	\n\n *Powered by the Square Python SDK and the Loyalty API.* \
	\nMIT License. [Opensource GitHub Repo](https://github.com/anqkhieu/SquareStarbot).", colour=discord.Colour.orange())
	await ctx.send(embed=embed)

# Show the Command List
@client.command(aliases=['commands'])
async def help(ctx):
	embed = discord.Embed(description = ":robot:  **ALL COMMANDS**\n\n", colour=discord.Colour.orange())
	embed.add_field(name='`!profile` or `!mystats`',
					value=f'Shows your current level, exp, and earned {pointsName}.', inline=False)
	embed.add_field(name='`!rewards` or `!loyalty`',
					value='Lists rewards one can earn from the loyalty program.', inline=False)
	embed.add_field(name='`!link`',
					value=f'Must be used in direct messages with the bot. Associates your account with our loyalty rewards program to earn {pointsName}.', inline=False)
	embed.add_field(name='`!gift`',
					value=f'Only usable by those with administrator priviledges. Gifts a specificed number of {pointsName} to tagged users. (Eg: `!gift 200 Stars @Username`)', inline=False)
	embed.add_field(name='`!about` or `!what`',
					value='Tells you about this awesome bot.', inline=False)
	embed.add_field(name='`!help` or `!commands`',
					value='Shows you the command list.', inline=False)
	await ctx.send(embed=embed)

# Square API Utility Functions ----------------------------------------
def CreateLoyaltyAccount(phone_map):
	result = square_client.loyalty.create_loyalty_account(body = {"loyalty_account": {"program_id": os.getenv('SQUARE_LOYALTY_PROGRAM_ID'), "mapping": {"phone_number": phone_map}}, "idempotency_key": str(uuid.uuid1())})

	if result.is_success():
		return True, result.body
	elif result.is_error():
		print(result.errors)
		return False, result.body

def AddLoyaltyPoints(id, amount, reason='None'):
	# Add Square Loyalty Points
	loyalty_account_id = profiles.find_one({'_id': id})['loyalty_account_id']
	body = {}
	body['idempotency_key'] = str(uuid.uuid1())
	body['adjust_points'] = {}
	body['adjust_points']['loyalty_program_id'] = os.getenv('SQUARE_LOYALTY_PROGRAM_ID')
	body['adjust_points']['points'] = amount
	body['adjust_points']['reason'] = reason

	result = loyalty_api.adjust_loyalty_points(loyalty_account_id, body)
	if result.is_success(): pass
	elif result.is_error(): print(result.errors)

# Other Utility Functions --------------------------------------------
async def RequestLoyaltyAccountLinkage(member):
	content = f"🌟   **ARE YOU IN OUR LOYALTY REWARDS PROGRAM?**\
	\n\nFor being a positive, active community member on this Discord server, you can also earn loyalty points to our [merch store](https://squareup.com/us/en)! \
	\n\
	\nTo enable loyalty rewards or connect your existing account, enter your phone number below. Just for doing so, you will earn **100 {pointsName} for free**! If not now, you can use the `!link` command in the future to enroll into our loyalty rewards program.\
	\n\
	\n:calling: **ENTER YOUR PHONE NUMBER BELOW**\
	\nExample: +1(123)456-7890"

	embed = discord.Embed(description=content, colour=discord.Colour.orange())
	await member.send(embed=embed)

	try:
		def check(m): return m.author == member
		reply = await client.wait_for('message', timeout=300.0, check=check)
	except asyncio.TimeoutError: return

	# Look up if loyalty account exists by phone number
	phone = '+' + ''.join(filter(str.isdigit, reply.content))
	result = square_client.loyalty.search_loyalty_accounts(body = {"query": {"mappings": [{"phone_number": phone}]}})

	# Create a loyalty account if none exists with phone number
	if result.body == {}:
		content = f"We could not find an existing loyalty rewards account. Would you like to create one associated with this phone number?"
		embed = discord.Embed(description=content, colour=discord.Colour.orange())
		message = await member.send(embed=embed)
		await message.add_reaction('👍')
		await message.add_reaction('👎')

		def check(reaction, user): return member == user

		try:
			reaction, user = await client.wait_for('reaction_add', timeout=300.0, check=check)
		except asyncio.TimeoutError:
			content = "Your session timed out. In the future, you can use the `!link` command to associate your phone number with your account and become eligible to receive loyalty rewards."
			embed = discord.Embed(description=content, colour=discord.Colour.red())
			await member.send(embed=embed)
			return
		else:
			if str(reaction) == '👍':
				content =f"Awesome, we will now set up a loyalty account associated with {phone}. Please wait."
				embed = discord.Embed(description=content, colour=discord.Colour.orange())
				await member.send(embed=embed)

				success, result = CreateLoyaltyAccount(phone)
				if success:
					content = f"You are now all set to earn {pointsName} for our merch store for community contributions on our Discord server. We hope you enjoy your stay and have lots of fun. :sunglasses: \
					\
					You've been rewarded 100 {pointsName} for linking your Discord and phone number! You can try using the `!profile` commands to see how many {pointsName} you have so far, or the `!rewards` command to see what you can redeem your {pointsName} for in our [merch store](https://placeholder.org)."
					embed = discord.Embed(description=content, colour=discord.Colour.green())
					await member.send(embed=embed)
					AddLoyaltyPoints(member.id, 100, reason='Linked Discord account and phone number.')

					key = {'_id': member.id}
					value = {'loyalty_account_id': success.body['loyalty_account']['id']}
					profiles.update_one(key, {"$set": value}, upsert=True)
					return
				else:
					error = result['errors'][0]
					title = f":scream:  **UH OH, ERROR!**"
					content = f"*Code:* {error['code']} \n*Category:* {error['detail']}\n\nPlease contact a staff member for assistance or try again by using the `!link` command."
					embed = discord.Embed(title=title, description=content, colour=discord.Colour.red())
					await member.send(embed=embed)
			else:
				content = f"Alright! In the future if you would ever like to create a loyalty account or associate an existing account, you can by entering the `!link` command in direct messages with this bot. :slight_smile:"
				embed = discord.Embed(description=content, colour=discord.Colour.orange())
				await member.send(embed=embed)

	else: # Matched existing loyalty account with phone number.
		time.sleep(1)
		content = f"Awesome, we found your existing loyalty rewards account! You are now all set to earn {pointsName} for our merch store for community contributions on our Discord server. We hope you enjoy your stay and have lots of fun. :sunglasses: \
		\
		You've been rewarded 100 {pointsName} for linking your account! Try using the `!profile` commands to see how many {pointsName} you have so far, or the `!rewards` command to see what you can redeem your {pointsName} for in our merch store!"
		embed = discord.Embed(description=content, colour=discord.Colour.orange())
		await member.send(embed=embed)

		AddLoyaltyPoints(membe.id, 100, reason='Linked Discord account and phone number.')
		key = {'_id': member.id}
		value = {'loyalty_account_id': success.body['loyalty_account']['id']}
		profiles.update_one(key, {"$set": value}, upsert=True)

def ConvertSecondsToTime(seconds):
	seconds = seconds % (24 * 3600)
	hour = seconds // 3600
	seconds %= 3600
	minutes = seconds // 60
	seconds %= 60
	return "%d:%02d:%02d" % (hour, minutes, seconds)

def NextLevelFormula(level):
	return round((4 * (level ** 2)) / 5)

def GetLevelFromExp(exp):
	assumed_level = 1
	total_lvl_exp = 1

	while exp > total_lvl_exp:
		total_lvl_exp = NextLevelFormula(assumed_level)
		if exp >= total_lvl_exp:
			assumed_level += 1
		else:
			assumed_level -= 1
			return(assumed_level)

def CheckLevelUp(exp, id):
	current_lvl = GetLevelFromExp(exp)
	old_lvl = profiles.find_one({'_id': id})['level']
	if old_lvl == current_lvl: return False

	key = {"_id": id}
	value = {'level': current_lvl}
	profiles.update_one(key, {"$set": value}, upsert=True)
	return current_lvl

client.run(discordToken)
