# DeepDeep

DeepDeep is a private local AI assistant built from the design in the pasted DeepSeek conversation. It has:

- a local Qwen 2.5 1.5B instruct model;
- SQLite conversation memory and lightweight automatic facts;
- local document search over `.txt`, `.md`, `.py`, `.json`, and `.csv` files;
- a terminal interface and an optional Flask web interface;
- multiple saved conversations that can be switched or deleted in the browser;
- an offline-by-default runtime policy.
- automatic web research when Bing is reachable, fetching pages and citing source URLs.

## Plan

1. Get one small instruct model running locally.
2. Store conversations and user facts in SQLite.
3. Add local retrieval so your own files can ground answers.
4. Wrap it in a terminal interface first, then a Flask web interface.
5. Test the local pieces independently and make internet access explicit.
6. Later, improve quality with a larger model, streaming output, better retrieval, and optional fine-tuning.

## First setup

Create a virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The model needs to be downloaded once while internet is available:

```bash
python main.py --download-model
```

After that, regular launches use local files only and do not contact the internet:

```bash
python main.py
```

For a local browser interface (built with Flask):

```bash
python main.py --gui
```

Open http://127.0.0.1:5000 in your browser. The sidebar keeps each conversation
locally, so starting a new conversation does not clear earlier chats. Select an
earlier conversation to continue it, or delete that conversation and its messages.
User facts saved in local memory are shared across conversations.

New chats are automatically named from the first message (web-search commands use
the search text), while a title you rename manually is preserved. Set
`DEEPDEEP_AUTO_RENAME_CHATS=0` to keep the default `New conversation` title.

## Web research

Web access is detected automatically at startup by checking Bing. DeepDeep sets
`DEEPDEEP_ALLOW_WEB=1` when Bing is reachable and `DEEPDEEP_ALLOW_WEB=0`
otherwise:

```bash
python main.py
# or
python main.py --gui
```

Requests that appear to need fresh or external information (for example,
current events, news, weather, prices, recommendations, comparisons, or an
explicit request to look something up) search Bing before generating a response.
DeepDeep fetches readable text from the top results and includes inline
citations plus a `Sources` section with the original URLs. `/web your question`
remains available to force an explicit web-only request. If Bing is unreachable
at startup or a later search fails, automatic web search is disabled and local
chat continues normally.

While a response is being generated, the GUI shows the local processing stages
and elapsed time. It does not expose private chain-of-thought text; the local
model only provides its final answer.

The GUI composer can attach one or more UTF-8 text, Markdown, Python, JSON, or
CSV files (up to 2 MB each). Attachments are read by the local model for that
request and are not added to the persistent document index; use `/add path` when
you want a file to remain available through local retrieval.

Run `python main.py --check` to verify the Python runtime without loading the model.

## Add your own knowledge

Put files in `data/docs/`, then start DeepDeep and use `/add path/to/file` once. For example:

```text
/add data/docs/my-project-notes.md
```

The index is stored locally in `data/index.json`. No cloud vector database or embedding API is used.

## Commands

`/help`, `/clear`, `/remember key=value`, `/add path`, `/sources`, and `/quit` are available in the terminal chat. In the GUI, type `/` in the composer to open the command picker for `/clear`, `/remember`, `/add`, `/sources`, and `/web`.

## Important limits

This is a real local assistant, not a newly trained foundation model. The first useful milestone is a private model runner with memory and retrieval. Training your own model from scratch would require a large dataset, substantial GPU time, and a different project. You can later add LoRA fine-tuning if you want DeepDeep's tone or knowledge to become more specialized.
