#chalkboard mod bot

import discord
from discord.ext import commands
import datetime
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

# ------------------ STORAGE ------------------
settings = {}
modlogs = {}     # {guild_id: [cases]}
notes = {}       # {guild_id: {user_id: [notes]}}
persist_roles = {}  # roles saved on leave/join
active_moderations = {}  # timed bans/mutes

# ------------------ SETTINGS ------------------
def get_settings(gid):
    if gid not in settings:
        settings[gid] = {
            "mod_log_channel": None,
        }
    return settings[gid]

# ------------------ LOGGING ------------------
def log_action(guild, user, moderator, action, reason="None"):
    s = get_settings(guild.id)
    gid = guild.id

    case_id = len(modlogs.get(gid, [])) + 1

    entry = {
        "case": case_id,
        "user": user.id if hasattr(user, 'id') else user,
        "mod": moderator.id,
        "action": action,
        "reason": reason,
        "time": datetime.datetime.utcnow()
    }

    modlogs.setdefault(gid, []).append(entry)

    # send modlog
    if s["mod_log_channel"]:
        channel = guild.get_channel(s["mod_log_channel"])
        if channel:
            embed = discord.Embed(title=f"Case #{case_id} — {action}", color=0xff4444)
            embed.add_field(name="User", value=str(user))
            embed.add_field(name="Moderator", value=str(moderator))
            embed.add_field(name="Reason", value=reason)
            embed.timestamp = entry["time"]
            asyncio.create_task(channel.send(embed=embed))

# ------------------ COMMANDS ------------------
# CLEAN
@bot.command()
async def clean(ctx, amount: int = 50):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"Cleaned {amount} messages.", delete_after=5)

# KICK
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="None"):
    await member.kick(reason=reason)
    log_action(ctx.guild, member, ctx.author, "Kick", reason)
    await ctx.send(f"Kicked {member}.")

# BAN
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="None"):
    await member.ban(reason=reason)
    log_action(ctx.guild, member, ctx.author, "Ban", reason)
    await ctx.send(f"Banned {member}.")

# UNBAN
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="None"):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    log_action(ctx.guild, user, ctx.author, "Unban", reason)
    await ctx.send(f"Unbanned {user}.")

# MUTE
@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, time: str = None, *, reason="None"):
    duration = None
    if time:
        if time.endswith("m"): duration = datetime.timedelta(minutes=int(time[:-1]))
        if time.endswith("h"): duration = datetime.timedelta(hours=int(time[:-1]))
        if time.endswith("d"): duration = datetime.timedelta(days=int(time[:-1]))

    await member.timeout_for(duration, reason=reason)
    log_action(ctx.guild, member, ctx.author, "Mute", reason)
    await ctx.send(f"Muted {member}.")

# UNMUTE
@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member, *, reason="None"):
    await member.timeout_until(None)
    log_action(ctx.guild, member, ctx.author, "Unmute", reason)
    await ctx.send(f"Unmuted {member}.")

# WARN
@bot.command()
async def warn(ctx, member: discord.Member, *, reason="None"):
    log_action(ctx.guild, member, ctx.author, "Warn", reason)
    await ctx.send(f"Warned {member}: {reason}")

# WARNINGS
@bot.command()
async def warnings(ctx, member: discord.Member):
    data = [c for c in modlogs.get(ctx.guild.id, []) if c["user"] == member.id and c["action"] == "Warn"]
    if not data:
        return await ctx.send("No warnings.")

    msg = "\n".join([f"Case {c['case']}: {c['reason']}" for c in data])
    await ctx.send(msg)

# SOFTBAN
@bot.command()
@commands.has_permissions(ban_members=True)
async def softban(ctx, member: discord.Member, *, reason="None"):
    await member.ban(reason=reason)
    await ctx.guild.unban(member)
    log_action(ctx.guild, member, ctx.author, "Softban", reason)
    await ctx.send(f"Softbanned {member}.")

# DEAFEN
@bot.command()
@commands.has_permissions(deafen_members=True)
async def deafen(ctx, member: discord.Member):
    await member.edit(deafen=True)
    log_action(ctx.guild, member, ctx.author, "Deafen")
    await ctx.send(f"Deafened {member}.")

# UNDEAFEN
@bot.command()
@commands.has_permissions(deafen_members=True)
async def undeafen(ctx, member: discord.Member):
    await member.edit(deafen=False)
    log_action(ctx.guild, member, ctx.author, "Undeafen")
    await ctx.send(f"Undeafened {member}.")

# MODLOGS (user)
@bot.command(name="modlogs")
async def modlogs_cmd(ctx, member: discord.Member):
    logs = [c for c in modlogs.get(ctx.guild.id, []) if c["user"] == member.id]
    if not logs:
        return await ctx.send("No logs.")

    msg = "
".join([f"Case {c['case']} — {c['action']}: {c['reason']}" for c in logs])
    await ctx.send(msg)

# CASE lookup
@bot.command(name="case")
async def case_cmd(ctx, case_id: int):
    entries = modlogs.get(ctx.guild.id, [])
    for c in entries:
        if c["case"] == case_id:
            return await ctx.send(f"Case {case_id}: {c['action']} — {c['reason']}")
    await ctx.send("Case not found.")

# REASON update
@bot.command()
async def reason(ctx, case_id: int, *, new_reason: str):
    for c in modlogs.get(ctx.guild.id, []):
        if c["case"] == case_id:
            c["reason"] = new_reason
            await ctx.send(f"Updated reason for case {case_id}.")
            return
    await ctx.send("Case not found.")

# SETTINGS: set mod log channel
@bot.command()
async def setmodlog(ctx, channel: discord.TextChannel):
    s = get_settings(ctx.guild.id)
    s["mod_log_channel"] = channel.id
    await ctx.send(f"Mod log channel set to {channel.mention}")

# LOCK CHANNEL
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel=None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 Locked {channel.mention}")

# UNLOCK
@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel=None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 Unlocked {channel.mention}")

# NOTES: add
@bot.command()
async def note(ctx, member: discord.Member, *, text):
    notes.setdefault(ctx.guild.id, {}).setdefault(member.id, []).append(text)
    await ctx.send(f"Added note for {member}.")

# NOTES: list
@bot.command()
async def notes_cmd(ctx, member: discord.Member):
    user_notes = notes.get(ctx.guild.id, {}).get(member.id, [])
    if not user_notes:
        return await ctx.send("No notes.")
    msg = "
".join([f"{i+1}. {n}" for i,n in enumerate(user_notes)])
    await ctx.send(msg)

# NOTES: delnote
@bot.command()
async def delnote(ctx, member: discord.Member, note_id: int):
    user_notes = notes.get(ctx.guild.id, {}).get(member.id, [])
    if note_id < 1 or note_id > len(user_notes):
        return await ctx.send("Invalid note ID.")
    user_notes.pop(note_id-1)
    await ctx.send("Deleted note.")

# NOTES: clearnotes
@bot.command()
async def clearnotes(ctx, member: discord.Member):
    notes.get(ctx.guild.id, {}).pop(member.id, None)
    await ctx.send("Cleared notes.")

# MEMBER LIST BY ROLE
@bot.command()
async def members(ctx, role: discord.Role):
    m = [str(u) for u in role.members]
    if not m:
        return await ctx.send("No members in that role.")
    await ctx.send("
".join(m))

# ------------------ EVENTS ------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(os.getenv("BOT_TOKEN"))

# END OF MODERATION-ONLY BOT


