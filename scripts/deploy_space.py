"""Create/update an owner-private Gradio Space using an existing HF login.
Never uploads the workspace or original clinical files. No model secrets are uploaded.
"""
import argparse
import tempfile
from pathlib import Path
from huggingface_hub import HfApi
from prepare_space import prepare

p=argparse.ArgumentParser()
p.add_argument('--repo',required=True,help='Your Hugging Face username/space-name')
a=p.parse_args()
api=HfApi()
api.whoami()  # Fail before any mutation when not authenticated.
try:
    info=api.repo_info(a.repo,repo_type='space')
    if not info.private:
        raise SystemExit('This helper only updates private Spaces. Choose a private Space for deployment.')
except Exception as exc:
    from huggingface_hub.errors import RepositoryNotFoundError
    if not isinstance(exc,RepositoryNotFoundError): raise
    api.create_repo(a.repo,repo_type='space',space_sdk='gradio',private=True)
with tempfile.TemporaryDirectory() as tmp:
    folder=prepare(Path(tmp)/'source')
    api.upload_folder(repo_id=a.repo,repo_type='space',folder_path=folder,commit_message='Deploy evidence review demo')
print('Uploaded to Hugging Face Space:',a.repo)
print('Check the Space build logs. Configure model credentials in Settings > Secrets to enable live AI.')
