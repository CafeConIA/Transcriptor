#pip install tkinter
#pip install pydub
#pip install SpeechRecognition
#pip install concurrent.futures
#pip install PyAudio

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pydub import AudioSegment, silence
import os
import threading
import speech_recognition as sr
from io import BytesIO
from pydub.utils import which
import time
from concurrent.futures import ThreadPoolExecutor
import sys

# Configura las rutas a ffmpeg y ffprobe considerando PyInstaller (_MEIPASS)
if hasattr(sys, '_MEIPASS'):
    # Si estamos ejecutando desde el ejecutable creado por PyInstaller
    ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg/bin/ffmpeg.exe")
    ffprobe_path = os.path.join(sys._MEIPASS, "ffmpeg/bin/ffprobe.exe")
else:
    # Si estamos ejecutando el script normalmente
    ffmpeg_path = os.path.join(os.path.dirname(__file__), "ffmpeg/bin/ffmpeg.exe")
    ffprobe_path = os.path.join(os.path.dirname(__file__), "ffmpeg/bin/ffprobe.exe")

# Establece las rutas en pydub
AudioSegment.converter = which(ffmpeg_path)
AudioSegment.ffprobe = which(ffprobe_path)

# Variables de entorno para ffmpeg y ffprobe
os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)
os.environ["FFMPEG_BINARY"] = ffmpeg_path
os.environ["FFPROBE_BINARY"] = ffprobe_path

# Verificar que las rutas existen
if not os.path.isfile(ffmpeg_path):
    raise FileNotFoundError(f"No se encontró ffmpeg en {ffmpeg_path}")
if not os.path.isfile(ffprobe_path):
    raise FileNotFoundError(f"No se encontró ffprobe en {ffprobe_path}")

# Función para dividir el audio en segmentos en memoria
def dividir_audio_en_memoria(ruta_audio, duracion_segmento=20000):
    audio = AudioSegment.from_file(ruta_audio)
    segmentos = []
    for i in range(0, len(audio), duracion_segmento):
        segmento = audio[i:i + duracion_segmento]
        # Añadir un pequeño silencio al principio para el primer segmento
        if i == 0:
            segmento = AudioSegment.silent(duration=500) + segmento
        buffer = BytesIO()
        segmento.export(buffer, format="wav")
        buffer.seek(0)
        segmentos.append(buffer)
    return segmentos, len(audio)

# Función para transcribir un segmento de audio desde memoria
def transcribir_segmento(segmento):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(segmento) as source:
            audio_data = recognizer.record(source)
            texto = recognizer.recognize_google(audio_data, language="es-ES")
            return texto
    except sr.UnknownValueError:
        return "[No se pudo entender el audio]"
    except sr.RequestError:
        return "[Error al conectarse al servicio de reconocimiento de Google]"

# Función para procesar todo el audio en memoria con barra de progreso
def transcribir_audio(ruta_audio, duracion_segmento, progress_bar, progress_label):
    # Convertir a WAV si es necesario
    archivo_convertido = None
    if not ruta_audio.endswith(".wav"):
        archivo_convertido = convertir_a_wav(ruta_audio)
        ruta_audio = archivo_convertido
    
    try:
        segmentos, total_duracion = dividir_audio_en_memoria(ruta_audio, duracion_segmento)
        num_segmentos = len(segmentos)

        transcripcion_completa = []
        progress_label["text"] = "Procesando segmentos en paralelo..."

        # Ejecutar la transcripción en paralelo utilizando ThreadPoolExecutor
        with ThreadPoolExecutor() as executor:
            future_to_segment = {executor.submit(transcribir_segmento, segmento): i for i, segmento in enumerate(segmentos)}

            for i, future in enumerate(future_to_segment):
                try:
                    result = future.result()
                    if i == 0 and (result == "" or "[No se pudo entender el audio]" in result):
                        # Reintentar si el primer segmento no fue entendido
                        result = transcribir_segmento(segmentos[i])
                    transcripcion_completa.append(result)
                except Exception as e:
                    transcripcion_completa.append(f"[Error en el segmento {i}] {e}")

                # Actualizar barra de progreso
                progress_bar["value"] = ((i + 1) / num_segmentos) * 100
                progress_label["text"] = f"Procesando segmento {i + 1} de {num_segmentos}..."
                progress_bar.update()
                time.sleep(0.1)  # Simular procesamiento

        progress_label["text"] = "¡Transcripción completa!"
        return " ".join(transcripcion_completa).strip()

    finally:
        # Si se creó un archivo temporal, eliminarlo
        if archivo_convertido and os.path.exists(archivo_convertido):
            os.remove(archivo_convertido)

# Función para convertir audio a formato WAV
def convertir_a_wav(ruta_audio):
    archivo_wav = "audio_convertido.wav"
    try:
        audio = AudioSegment.from_file(ruta_audio)
        audio.export(archivo_wav, format="wav")
    except Exception as e:
        raise RuntimeError(f"Error al procesar el audio: {e}")
    return archivo_wav

# Función para mostrar el resultado en una ventana aparte
def mostrar_resultado(texto, archivo_audio):
    ventana_resultado = tk.Toplevel(root)
    ventana_resultado.title("Resultado de la Transcripción")
    ventana_resultado.geometry("700x500")

    # Campo de texto para mostrar la transcripción
    text_widget = tk.Text(ventana_resultado, wrap=tk.WORD)
    text_widget.insert("1.0", texto)
    text_widget.configure(state="normal")
    text_widget.pack(expand=True, fill="both", padx=10, pady=10)

    # Botón para copiar al portapapeles
    def copiar_al_portapapeles():
        root.clipboard_clear()
        root.clipboard_append(texto)
        root.update()
        messagebox.showinfo("Copiado", "Texto copiado al portapapeles.")

    copiar_boton = ttk.Button(ventana_resultado, text="Copiar al Portapapeles", command=copiar_al_portapapeles)
    copiar_boton.pack(pady=5)

    # Botón para guardar en un archivo
    def guardar_como_txt():
        nombre_txt = os.path.splitext(archivo_audio)[0] + ".txt"
        with open(nombre_txt, "w", encoding="utf-8") as f:
            f.write(texto)
        messagebox.showinfo("Guardado", f"Transcripción guardada como {nombre_txt}.")

    guardar_boton = ttk.Button(ventana_resultado, text="Guardar como .txt", command=guardar_como_txt)
    guardar_boton.pack(pady=5)

# Función para procesar audio en un hilo
def procesar_audio_en_hilo(archivo, duracion_segmento, progress_bar, progress_label):
    try:
        texto = transcribir_audio(archivo, duracion_segmento, progress_bar, progress_label)
        mostrar_resultado(texto, archivo)
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error: {e}")

# Función para seleccionar archivo y procesar
def procesar_audio():
    archivo = filedialog.askopenfilename(
        title="Seleccionar archivo de audio",
        filetypes=[("Archivos de audio", "*.mp3 *.wav *.ogg *.flac")]
    )
    if archivo:
        try:
            duracion = int(duracion_segmento_entry.get()) * 1000  # Convertir segundos a milisegundos
        except ValueError:
            messagebox.showerror("Error", "Por favor, ingrese una duración válida en segundos.")
            return

        progress_bar["value"] = 0
        progress_label["text"] = "Procesando..."

        # Ejecutar la transcripción en un hilo para evitar que la ventana se congele
        threading.Thread(
            target=procesar_audio_en_hilo,
            args=(archivo, duracion, progress_bar, progress_label),
            daemon=True
        ).start()

# Configuración principal de la ventana
root = tk.Tk()
root.title("Transcriptor de Audio")
root.geometry("500x400")

# Etiqueta principal
label = tk.Label(root, text="Seleccione un archivo de audio para transcribir:", font=("Arial", 12))
label.pack(pady=10)

# Campo para ingresar duración de los segmentos
duracion_segmento_label = tk.Label(root, text="Dividir audio en segmentos de (segundos):", font=("Arial", 10))
duracion_segmento_label.pack(pady=5)

duracion_segmento_entry = ttk.Entry(root, font=("Arial", 10))
duracion_segmento_entry.insert(0, "20")  # Valor predeterminado: 20 segundos
duracion_segmento_entry.pack(pady=5)

# Botón para seleccionar archivo
boton = ttk.Button(root, text="Seleccionar Archivo", command=procesar_audio)
boton.pack(pady=10, ipadx=10, ipady=5)

# Barra de progreso
progress_bar = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
progress_bar.pack(pady=10)

# Etiqueta para mostrar el estado del progreso
progress_label = tk.Label(root, text="", font=("Arial", 10))
progress_label.pack(pady=5)

# Ejecutar la ventana principal
root.mainloop()
