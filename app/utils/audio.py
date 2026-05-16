import io
import static_ffmpeg
from pydub import AudioSegment

static_ffmpeg.add_paths()  # ffmpeg 바이너리 자동 등록

def convert_to_wav(audio_bytes: bytes, input_format: str = "m4a") -> bytes:
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    return wav_io.getvalue()