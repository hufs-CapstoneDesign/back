import io
import static_ffmpeg
from pydub import AudioSegment

static_ffmpeg.add_paths()

def convert_to_wav(audio_bytes: bytes, input_format: str = "mp3") -> bytes:
    """음성 파일을 WAV로 변환 (16kHz, mono)"""
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    return wav_io.getvalue()