import os

def load_diarization():

    token = os.getenv("PYANNOTE_AUTH_TOKEN")

    if not token:
        print("pyannote: auth token not set")
        return None

    try:
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization",
            token=token
        )

        print("pyannote diarization loaded")
        return pipeline

    except Exception as e:
        print("pyannote pipeline load error:", e)
        return None
