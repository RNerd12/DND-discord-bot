import traceback
import discord
from discord.ext import commands
import Secrets
import json
from firebase_logger import FirebaseClient

meta_file = "meta.json"
meta_collection = "metadata"

# Firebase setup
fclient = FirebaseClient(Secrets.FIREBASE_CRED_PATH)

# Discord setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


# util functions
def get_preference_firestore():
    data = fclient.get_preference(meta_collection)
    with open(meta_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def save_preference(guild_id, preference_type, preference_id):
    with open(meta_file, "r") as file:
        data = json.load(file)
    data[str(guild_id)][preference_type] = preference_id
    fclient.set_preference(data, meta_collection)
    with open(meta_file, "w") as file:
        json.dump(data, file, indent=4)


def get_preference(guild_id, key: str):
    with open(meta_file, "r") as file:
        data = json.load(file)
        return data.get(str(guild_id), {}).get(key)


def log_firebase(ctx: commands.Context, players: list[discord.Member]):
    fcollection = fclient.get_collection(str(ctx.guild.id))
    return fclient.log_players(fcollection, players)


def get_roles(ctx: commands.Context, role_name: str):
    roles = get_preference(ctx.guild.id, role_name)
    for role_id in roles:
        for i in ctx.guild.roles:
            if i.id == role_id:
                yield i
                break


async def send_message(ctx: commands.Context, message: str):
    channel_id = get_preference(ctx.guild.id, "output_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
        else:
            await ctx.send("Output channel is not set or not found.")
    else:
        await ctx.send(message)


# setup
@bot.event
async def on_ready():
    print("-" * 50)
    print(f"{bot.user} has connected to Discord!")
    get_preference_firestore()
    print("retreived")
    print("-" * 50)


# test command
@bot.command(name="hello")
async def on_hello(ctx: commands.Context):
    print("-" * 50)
    print("printing hello")
    await send_message(ctx, "hello")
    print("-" * 50)


# server specific setup
@bot.command(name="setrole")
async def set_role(ctx: commands.Context, role_for: str, *roles: discord.Role):
    print("-" * 50)
    if role_for == "player":
        save_preference(ctx.guild.id, "player_role", [role.id for role in roles])
    elif role_for == "gm":
        save_preference(ctx.guild.id, "gm_role", [role.id for role in roles])
    elif role_for == "suspend":
        save_preference(ctx.guild.id, "suspended_role", [role.id for role in roles])
    elif role_for == "mod":
        save_preference(ctx.guild.id, "mod_role", [role.id for role in roles])
    else:
        await send_message(ctx, "select valid rolefor : player, gm, suspended, mod")
        print("select valid option")
        print("-" * 50)
        return
    print(f"set role for {role_for}")
    for role in roles:
        if role.mentionable:
            await send_message(ctx, f"{role_for} role set to {role.mention}")
        else:
            await send_message(ctx, f"{role_for} role set to {role.name}")
    print("-" * 50)


@bot.command(name="setchannel")
async def set_channel(ctx: commands.Context, channel: discord.TextChannel):
    save_preference(ctx.guild.id, "channel", channel.id)
    await send_message(ctx, f"Output channel set to {channel.mention}")

@bot.command(name="setreactrolemessage")
async def set_reactrolemessage(ctx: commands.Context, channel_id: int, message_id: int):
    try:
        reactrole_channel = bot.get_channel(channel_id)
        # Fetch the message from any channel
        reactrole_message = await reactrole_channel.fetch_message(message_id)
        save_preference(ctx.guild.id, "reactrole_message", reactrole_message.id)
        save_preference(ctx.guild.id, "reactrole_channel", reactrole_channel.id)
        await send_message(ctx, f"Reacttrole channel set to {reactrole_channel.mention}")
        await send_message(ctx, f"Reacttrole message set to {reactrole_message.jump_url}")
    except discord.NotFound:
        await ctx.send("Message not found.")

@bot.command(name="loadmembers")
async def set_logger(ctx: commands.Context):
    print("-" * 50)
    player_roles = list(get_roles(ctx, "player_role"))
    if player_roles:
        dnd_players = [
            i
            for i in ctx.guild.members
            for player_role in player_roles
            if (not i.bot) and (player_role in i.roles)
        ]
        count = log_firebase(ctx, dnd_players)
        print(f"{count} players logged")
        await send_message(ctx, f"{count} players logged")
    else:
        await send_message(ctx, "Player role not set, set it with !setplayerrole")
    print("-" * 50)


# logging
@bot.command(name="logsession")
async def log_session(ctx: commands.Context, time, *players: discord.Member):
    print("-" * 50)
    gm_roles = list(get_roles(ctx, "gm_role"))
    if not gm_roles:
        await send_message(ctx, "No gm role set")
        print("No gm role set")
    elif gm_roles[0] not in ctx.author.roles:
        await send_message(ctx, "Command can only be used by gms")
        print("Command can only be used by gms")
    elif not players:
        await send_message(ctx, "No players entered")
        print("No players entered")
    else:
        fcollection = fclient.get_collection(str(ctx.guild.id))
        try:
            fclient.log_session(fcollection, list(players), ctx.author, time)
        except ValueError as e:
            await send_message(ctx, str(e))
            traceback.print_exc()
        message = "Session logged for:\n"
        ps = [i.id for i in players]
        print(f"logged session for : {ps}")
        for i in players:
            message += f"{i.name}\n"
        message += f"session logged by {ctx.author.name}\n"
        await send_message(ctx, message)
    print("-" * 50)


# purging
@bot.command(name="purgeinactive")
async def purge_inactive(ctx: commands.Context):
    print("-" * 50)
    mod_roles = list(get_roles(ctx, "mod_role"))
    if mod_roles[0] not in ctx.author.roles:
        print("insufficient permissions")
        await send_message(ctx, "you must be a mod to run this command")
        return
    player_roles = list(get_roles(ctx, "player_role"))
    gm_roles = list(get_roles(ctx, "gm_role"))
    suspended_roles = list(get_roles(ctx, "suspended_role"))
    if player_roles and mod_roles and gm_roles and suspended_roles:
        test_players = []
        for player_role in player_roles:
            test_players.extend(
                [
                    i
                    for i in ctx.guild.members
                    if (player_role in i.roles) and (mod_roles[0] not in i.roles) and (not i.bot)
                ]
            )
        fcollection = fclient.get_collection(str(ctx.guild.id))
        inactive = fclient.get_inactive_players(fcollection, test_players)
        message = "purged : \n"
        for player in inactive:
            await player.remove_roles(*player_roles, *gm_roles)
            await player.add_roles(*suspended_roles)
            print(f"removed roles for {player.name}")
            message += f"{player.name}\n"
        await send_message(ctx, message)
    else:
        print("set valid player, mod, gm and suspended roles!")
        await send_message(ctx, "set valid player, mod, gm and suspended roles!")
    print("-" * 50)


@bot.command(name="rolecleanup")
async def role_cleanup(ctx: commands.Context):
    print("-" * 50)
    mod_roles = list(get_roles(ctx, "mod_role"))
    if mod_roles[0] not in ctx.author.roles:
        print("insufficient permissions")
        await send_message(ctx, "you must be a mod to run this command")
        return
    reactrole_channel_id = get_preference(ctx.guild.id, "reactrole_channel")
    reactrole_message_id = get_preference(ctx.guild.id, "reactrole_message")
    try:
        reactrole_channel = bot.get_channel(reactrole_channel_id)
        # Fetch the message from any channel
        reactrole_message = await reactrole_channel.fetch_message(reactrole_message_id)
    except discord.NotFound:
        await ctx.send("Message not found.")
    suspended_roles = list(get_roles(ctx, "suspended_role"))
    for reaction in reactrole_message.reactions:
        async for user in reaction.users():
            member = ctx.guild.get_member(user.id)
            if member is None or any(role in member.roles for role in suspended_roles):
                try:
                    print(f"removed {reaction.emoji} reaction for {user.global_name}")
                    await reaction.remove(user)
                except discord.Forbidden:
                    await ctx.send(f"I don't have the necessary permissions to remove reactions for {user.display_name}.")
    await ctx.send(f"Removed reactions from all users with the {suspended_roles[0].name} role on the {reactrole_message.jump_url} message.")

@bot.command(name="purgeinactivegm")
async def purge_inactive_gm(ctx: commands.Context):
    print("-" * 50)
    mod_roles = list(get_roles(ctx, "mod_role"))
    if mod_roles[0] not in ctx.author.roles:
        print("insufficient permissions")
        await send_message(ctx, "you must be a mod to run this command")
        return
    gm_roles = list(get_roles(ctx, "gm_role"))
    if mod_roles and gm_roles:
        test_gms = []
        for gm_role in gm_roles:
            test_gms.extend(
                [
                    i
                    for i in ctx.guild.members
                    if (gm_role in i.roles) and (mod_roles[0] not in i.roles) and (not i.bot)
                ]
            )
        fcollection = fclient.get_collection(str(ctx.guild.id))
        inactive = fclient.get_inactive_gms(fcollection, test_gms)
        message = "purged gms : \n"
        for gm in inactive:
            await gm.remove_roles(*gm_roles)
            print(f"removed role for {gm.name}")
            message += f"{gm.name}\n"
        await send_message(ctx, message)
    else:
        print("set valid mod, gm and suspended roles!")
        await send_message(ctx, "set valid mod, gm and suspended roles!")
    print("-" * 50)


bot.run(Secrets.BOT_TOKEN)
