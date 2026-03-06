import os

def load_pipeline():

    token = os.getenv("PYANNOTE_AUTH_TOKEN")

    if not token:
        print("pyannote: token not set")
        return None

    try:
        from pyannote.audio import Pipeline

        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization",
            token=token
        )

        print("pyannote diarization loaded")

        return pipe

    except Exception as e:
        print("pyannote pipeline load error:", e)
        return None
