import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp  # Asegúrate de tenerlo instalado: pip install youtube_dl
import asyncio

# Configuración del token y application ID
TOKEN = 'MTM2ODQ2MTI3MzI2Mzc2NzYyMg.GyXqxq.ThZLxmwcrHEHz3WOhwBobuCnv4_iA8ZcEjyjHs'  # Reemplazar con tu token de bot de Discord
CLIENT_ID = '1368461273263767622'  # Reemplazar con tu application ID

# Opciones de yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'before_options': '-reconnect 1 -stream_loop -1',  # Reconexión y loop
    'noplaylist': True,  # No descargar listas de reproducción
    'nocheckcertificate': True,  # Para evitar errores de certificado SSL
    'source_address': '0.0.0.0',  # Para problemas de enlace
}

# Inicialización del cliente con intents necesarios
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.messages = True  # Si necesitas leer mensajes
bot = commands.Bot(command_prefix="!", intents=intents)

# Estructuras de datos para almacenar colas de reproducción
queues = {}

# Función auxiliar para formatear duración
def format_duration(seconds):
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02}"

@bot.event
async def on_ready():
    print(f'Bot iniciado como {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

# Comando /play en Python
@bot.tree.command(name='play', description='Reproduce una canción desde YouTube')
async def play(interaction: discord.Interaction, consulta: str):
    # Verificar si el usuario está en un canal de voz
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message('Necesitas estar en un canal de voz para usar este comando.', ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel

    # Verificar permisos (en Python, discord.py maneja esto en la conexión)
    permissions = voice_channel.permissions_for(interaction.guild.me)  # Usa interaction.guild.me
    if not permissions.connect or not permissions.speak:
        await interaction.response.send_message('No tengo permisos para conectarme o hablar en este canal de voz.', ephemeral=True)
        return

    # Verificar término de búsqueda
    if not consulta:
        await interaction.response.send_message('Necesitas proporcionar un término de búsqueda.', ephemeral=True)
        return

    await interaction.response.defer()  # Defer para evitar el timeout

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: #cambiado a yt_dlp
            # Buscar video en YouTube
            info = ydl.extract_info(f"ytsearch:{consulta}", download=False)
            if not info['entries']:
                await interaction.followup.send(content='No se encontraron resultados.')
                return
            video = info['entries'][0]  # Toma el primer resultado
            song = {
                'title': video.get('title'),
                'url': video.get('url'),
                'duration': format_duration(video.get('duration', 0)),
                'thumbnail': video.get('thumbnail'),
                'requested_by': interaction.user.name
            }

        # Obtener o crear la cola de reproducción del servidor
        guild_id = interaction.guild.id
        if guild_id not in queues:
            queues[guild_id] = {
                'voice_channel': voice_channel,
                'text_channel': interaction.channel,  # Usar interaction.channel
                'connection': None,
                'songs': [],
                'volume': 0.5,
                'playing': True,
                'loop': False #añadido loop
            }

        server_queue = queues[guild_id]
        server_queue['songs'].append(song)

        if not server_queue['connection'] or not server_queue['connection'].is_connected(): #si no esta conectado o no hay conexion
            try:
                # Unirse al canal de voz
                connection = await voice_channel.connect()
                server_queue['connection'] = connection
                await play_song(guild_id, interaction) #pasar interaction
            except Exception as e:
                print(f'Error al unirme al canal de voz: {e}')
                del queues[guild_id]
                await interaction.followup.send(f'Error al unirme al canal de voz: {e}')
                return
        else:
             # Informar que se agregó a la cola
            embed = discord.Embed(
                title='Añadido a la cola',
                description=f"**{song['title']}**",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=song['thumbnail'])
            embed.add_field(name='Duración', value=song['duration'])
            embed.add_field(name='Solicitado por', value=song['requested_by'])
            await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f'Error en el comando play: {e}')
        await interaction.followup.send(f'Error al procesar la solicitud: {e}')

async def play_song(guild_id, interaction: discord.Interaction): #pasar interaction
    server_queue = queues.get(guild_id)
    if not server_queue or not server_queue['songs']:
        if server_queue and server_queue['connection']:
            await server_queue['connection'].disconnect()
        queues.pop(guild_id, None)
        return

    current_song = server_queue['songs'][0]

    try:
        # Crear recurso de audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: #cambiado a yt_dlp
            info = ydl.extract_info(current_song['url'], download=False)
            url = info.get('url')
        
        #source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **{'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}), volume=server_queue['volume'])
        source = discord.FFmpegPCMAudio(url)
        server_queue['connection'].play(source, after=lambda error: handle_after(guild_id, interaction, error)) #pasar interaction

        # Informar sobre la canción actual
        embed = discord.Embed(
            title='Reproduciendo ahora',
            description=f"**{current_song['title']}**",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=current_song['thumbnail'])
        embed.add_field(name='Duración', value=current_song['duration'])
        embed.add_field(name='Solicitado por', value=current_song['requested_by'])
        await server_queue['text_channel'].send(embed=embed)

    except Exception as e:
        print(f'Error al reproducir canción: {e}')
        await server_queue['text_channel'].send(f'Error al reproducir: {e}')
        server_queue['songs'].pop(0)
        await play_song(guild_id, interaction) #pasar interaction

def handle_after(guild_id, interaction: discord.Interaction, error): #pasar interaction
    if error:
        print(f'Error al reproducir la canción: {error}')
    server_queue = queues.get(guild_id)
    if server_queue:
        if server_queue['loop']:
            asyncio.run_coroutine_threadsafe(play_song(guild_id, interaction), bot.loop) #cambiado client por bot
        else:
            server_queue['songs'].pop(0)
            asyncio.run_coroutine_threadsafe(play_song(guild_id, interaction), bot.loop) #cambiado client por bot

# Comando /skip en Python
@bot.tree.command(name='skip', description='Salta a la siguiente canción en la cola') #cambiado client por bot
async def skip(interaction: discord.Interaction):
    # Verificar si el usuario está en un canal de voz
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message('Necesitas estar en un canal de voz para usar este comando.', ephemeral=True)
        return

    server_queue = queues.get(interaction.guild.id)
    if not server_queue:
        await interaction.response.send_message('No hay canciones en la cola.', ephemeral=True)
        return

    if not server_queue['connection'] or not server_queue['connection'].is_connected():
        await interaction.response.send_message('No estoy conectado a un canal de voz.', ephemeral=True)
        return

    server_queue['connection'].stop()
    await interaction.response.send_message('⏭️ Canción saltada.')

# Comando /stop en Python
@bot.tree.command(name='stop', description='Detiene la reproducción y desconecta el bot') #cambiado client por bot
async def stop(interaction: discord.Interaction):
    # Verificar si el usuario está en un canal de voz
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message('Necesitas estar en un canal de voz para usar este comando.', ephemeral=True)
        return

    server_queue = queues.get(interaction.guild.id)
    if not server_queue:
        await interaction.response.send_message('No hay canciones en reproducción.', ephemeral=True)
        return
    
    if not server_queue['connection'] or not server_queue['connection'].is_connected():
        await interaction.response.send_message('No estoy conectado a un canal de voz.', ephemeral=True)
        return

    # Limpiar cola y desconectar
    server_queue['songs'] = []
    server_queue['connection'].stop()
    await server_queue['connection'].disconnect()
    queues.pop(interaction.guild.id, None) #eliminar la queue
    await interaction.response.send_message('⏹️ Reproducción detenida y desconectado.')

# Comando /queue en Python
@bot.tree.command(name='queue', description='Muestra la cola de reproducción actual') #cambiado client por bot
async def queue_command(interaction: discord.Interaction):
    server_queue = queues.get(interaction.guild.id)
    if not server_queue or not server_queue['songs']:
        await interaction.response.send_message('No hay canciones en la cola.', ephemeral=True)
        return

    # Crear embed con la cola
    embed = discord.Embed(
        title='Cola de reproducción',
        description='Lista de canciones en cola:',
        color=discord.Color.blue()
    )

    # Añadir información de la canción actual
    embed.add_field(
        name='🎵 Reproduciendo ahora:',
        value=f"**{server_queue['songs'][0]['title']}** | {server_queue['songs'][0]['duration']} | Solicitado por: {server_queue['songs'][0]['requested_by']}",
        inline=False
    )

    # Añadir el resto de canciones en cola (hasta 10)
    if len(server_queue['songs']) > 1:
        queue_text = ''
        songs_to_show = min(len(server_queue['songs']) - 1, 10)
        for i in range(1, songs_to_show + 1):
            song = server_queue['songs'][i]
            queue_text += f"{i}. **{song['title']}** | {song['duration']} | Solicitado por: {song['requested_by']}\n"
        if len(server_queue['songs']) > 11:
            queue_text += f"\n... y {len(server_queue['songs']) - 11} canciones más."
        embed.add_field(name='📋 Próximas canciones:', value=queue_text, inline=False)
    else:
        embed.add_field(name='📋 Próximas canciones:', value='No hay más canciones en cola.', inline=False)

    await interaction.response.send_message(embed=embed)

# Comando /help en Python
@bot.tree.command(name='help', description='Muestra información de ayuda sobre los comandos') #cambiado client por bot
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title='Comandos del Bot de Música',
        description='Lista de comandos disponibles:',
        color=discord.Color.blue()
    )
    embed.add_field(name='/play <consulta>', value='Reproduce una canción o la añade a la cola', inline=False)
    embed.add_field(name='/skip', value='Salta a la siguiente canción en la cola', inline=False)
    embed.add_field(name='/stop', value='Detiene la reproducción y desconecta el bot', inline=False)
    embed.add_field(name='/queue', value='Muestra la cola de reproducción actual', inline=False)
    embed.add_field(name='/help', value='Muestra este mensaje de ayuda', inline=False)
    await interaction.response.send_message(embed=embed)

#Comando loop
@bot.tree.command(name="loop", description="Activa/desactiva el bucle de la canción actual") #cambiado client por bot
async def loop(interaction: discord.Interaction):
    server_queue = queues.get(interaction.guild.id)
    if not server_queue:
        await interaction.response.send_message("No hay nada en reproducción.", ephemeral=True)
        return

    server_queue['loop'] = not server_queue['loop']  # Cambia el estado del bucle
    if server_queue['loop']:
        await interaction.response.send_message("Loop activado 🔂", ephemeral=True)
    else:
        await interaction.response.send_message("Loop desactivado 🔁", ephemeral=True)

# Iniciar sesión con el token
bot.run(TOKEN) #cambiado client por bot
