# Workflow: Reading Literature

## Discovery

1. **Run paper harvester** to find new papers:
   ```bash
   python3 -m paperscope harvest
   ```

2. **Review the digest** at `~/Papers/harvester/inbox/YYYY-MM-DD/digest.md`

3. **Triage**: Keep relevant papers, archive the rest.

## Structured Reading

For papers you keep:

1. **Extract text** from the PDF:
   ```python
   from paperscope.ingest.extract_text import extract_text
   text = extract_text(Path("paper.pdf"), Path("text/paper.txt"))
   ```

2. **Generate structured reading** using an LLM:
   ```python
   from paperscope.read.read_paper import create_reading_prompt
   prompt = create_reading_prompt(text, context="Relevant to information geometry work")
   # Feed prompt to Claude/GPT, save the structured output
   ```

3. **Embed claims** for later querying:
   ```python
   from paperscope.embed.embed_claims import embed_claims
   claims = [{"text": claim, "cite_key": key, "source": "paper_title"} for claim in extracted_claims]
   embeddings = embed_claims(claims)
   ```

## Depth-2 Harvesting

Once your bibliography is built, harvest references-of-references:

1. For each DOI in bibliography.json, query CrossRef for its reference list
2. Add new references as depth-2 entries
3. Resolve DOIs, acquire papers, extract text
4. This captures the extended intellectual neighborhood
