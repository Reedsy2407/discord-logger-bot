import discord
import aiohttp
import io
import datetime
import time
import os
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.members = True

from dotenv import load_dotenv
load_dotenv()

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

media_cache = {}
canales_notificados = set()

LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID"))
CANAL_TEXTO_ID = int(os.environ.get("CANAL_TEXTO_ID"))
CANAL_VOZ_ID = int(os.environ.get("CANAL_VOZ_ID"))
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")


async def notificar_zona_estudio(guild):
    canal_voz = guild.get_channel(CANAL_VOZ_ID)
    canal_texto = bot.get_channel(CANAL_TEXTO_ID)
    if not canal_voz or not canal_texto:
        return
    personas = len([m for m in canal_voz.members if not m.bot])
    if personas >= 2 and CANAL_VOZ_ID not in canales_notificados:
        canales_notificados.add(CANAL_VOZ_ID)
        rol = discord.utils.get(guild.roles, name="CONVOCADOS")
        mention = rol.mention if rol else "@CONVOCADOS"
        try:
            invite = await canal_voz.create_invite(max_age=0, max_uses=0)
            await canal_texto.send(
                f"🎙️ Hay gente en **CABEZA** {mention}\n\n<{invite.url}>"
            )
            print(f"🔊 Notificado: {canal_voz.name} con {personas} personas")
        except Exception as e:
            print(f"❌ Error al notificar: {e}")
            await canal_texto.send(
                f"🎙️ Hay gente en **CABEZA** {mention}"
            )


@tree.command(name="status", description="Muestra el estado del bot")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message("Que seil", ephemeral=True)


@bot.event
async def on_ready():
    print(f"✅ Bot activo como: {bot.user}")
    for guild in bot.guilds:
        await notificar_zona_estudio(guild)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Límite de cache: máximo 100 mensajes
    if len(media_cache) > 100:
        oldest = next(iter(media_cache))
        del media_cache[oldest]

    attachments_to_cache = []

    for att in message.attachments:
        filename_lower = att.filename.lower()

        is_audio = filename_lower.endswith((".ogg", ".mp3", ".wav", ".m4a", ".flac"))
        is_image = filename_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
        is_video = filename_lower.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv"))

        if is_audio or is_image or is_video:
            tipo = "audio" if is_audio else "image" if is_image else "video"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(att.url) as resp:
                        if resp.status == 200:
                            attachments_to_cache.append({
                                "bytes": await resp.read(),
                                "filename": att.filename,
                                "type": tipo
                            })
                            print(f"📦 Media cacheada: {att.filename} de {message.author}")
            except Exception as e:
                print(f"❌ Error al cachear {att.filename}: {e}")

    if attachments_to_cache:
        media_cache[message.id] = {
            "files": attachments_to_cache,
            "author": str(message.author),
            "channel": message.channel.mention,
            "timestamp": message.created_at
        }


@bot.event
async def on_message_delete(message):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    if message.id in media_cache:
        data = media_cache.pop(message.id)

        tipos = [f["type"] for f in data["files"]]
        if all(t == "audio" for t in tipos):
            emoji = "🎵"
            label = "Audio eliminado" if len(data["files"]) == 1 else "Audios eliminados"
        elif all(t == "image" for t in tipos):
            emoji = "🖼️"
            label = "Imagen eliminada" if len(data["files"]) == 1 else "Imágenes eliminadas"
        elif all(t == "video" for t in tipos):
            emoji = "🎬"
            label = "Video eliminado" if len(data["files"]) == 1 else "Videos eliminados"
        else:
            emoji = "📁"
            label = "Archivos eliminados"

        embed = discord.Embed(
            title=f"{emoji} {label} ({len(data['files'])})",
            color=discord.Color.red()
        )
        embed.add_field(name="Autor", value=data["author"], inline=True)
        embed.add_field(name="Canal", value=data["channel"], inline=True)
        embed.add_field(name="🗑️ Eliminado", value=f"<t:{now_ts}:f>", inline=True)
        embed.add_field(
            name="Archivos",
            value="\n".join(f["filename"] for f in data["files"]),
            inline=False
        )

        if message.reference and message.reference.resolved and hasattr(message.reference.resolved, 'content'):
            ref = message.reference.resolved
            ref_content = ref.content[:100] + "..." if len(ref.content) > 100 else ref.content
            embed.add_field(
                name="↩️ Respondía a",
                value=f"**{ref.author}**: {ref_content}",
                inline=False
            )

        files_to_send = [
            discord.File(fp=io.BytesIO(f["bytes"]), filename=f["filename"])
            for f in data["files"]
        ]

        await log_channel.send(embed=embed, files=files_to_send)
        return

    if message.content and not message.author.bot:
        embed = discord.Embed(
            title="🗑️ Mensaje eliminado",
            color=discord.Color.orange()
        )
        embed.add_field(name="Autor", value=str(message.author), inline=True)
        embed.add_field(name="Canal", value=message.channel.mention, inline=True)
        embed.add_field(name="🗑️ Eliminado", value=f"<t:{now_ts}:f>", inline=True)
        embed.add_field(name="Contenido", value=message.content, inline=False)

        if message.reference and message.reference.resolved and hasattr(message.reference.resolved, 'content'):
            ref = message.reference.resolved
            ref_content = ref.content[:100] + "..." if len(ref.content) > 100 else ref.content
            embed.add_field(
                name="↩️ Respondía a",
                value=f"**{ref.author}**: {ref_content}",
                inline=False
            )

        await log_channel.send(embed=embed)


@bot.event
async def on_bulk_message_delete(messages):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    embed = discord.Embed(
        title=f"🧹 Eliminación masiva ({len(messages)} mensajes)",
        color=discord.Color.dark_red()
    )
    embed.add_field(name="🗑️ Eliminado", value=f"<t:{now_ts}:f>", inline=True)

    resumen = []
    for msg in messages[:20]:
        if msg.content:
            resumen.append(f"**{msg.author}**: {msg.content[:50]}")
        elif msg.attachments:
            resumen.append(f"**{msg.author}**: [{msg.attachments[0].filename}]")

    if resumen:
        embed.add_field(name="Mensajes", value="\n".join(resumen), inline=False)

    await log_channel.send(embed=embed)


@bot.event
async def on_voice_state_update(member, before, after):
    print(f"🔊 Voice update: {member} | before: {before.channel} | after: {after.channel}")
    if member.bot:
        return

    if after.channel and after.channel.id == CANAL_VOZ_ID:
        await notificar_zona_estudio(member.guild)

    if before.channel and before.channel.id == CANAL_VOZ_ID:
        canal_voz = member.guild.get_channel(CANAL_VOZ_ID)
        if canal_voz:
            personas = len([m for m in canal_voz.members if not m.bot])
            if personas < 2 and CANAL_VOZ_ID in canales_notificados:
                canales_notificados.discard(CANAL_VOZ_ID)


retry_delay = 5
while True:
    try:
        bot.run(DISCORD_TOKEN)
        retry_delay = 5
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
        print(f"🔄 Reiniciando en {retry_delay} segundos...")
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 300)