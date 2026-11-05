"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import string
import math

# Words too common to count as evidence that a document answers the query
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
    "do", "does", "did", "i", "you", "we", "it", "this", "that", "these",
    "those", "of", "to", "in", "on", "at", "for", "from", "with", "by",
    "and", "or", "but", "not", "what", "where", "when", "which", "who",
    "whom", "why", "how", "can", "could", "should", "would", "will",
    "my", "your", "our", "me", "as", "if", "so", "than", "then", "there",
}

# Fraction of a query's meaningful words a document must contain to be used
MIN_MATCH_RATIO = 0.6

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for filename, text in documents:
            for word in text.lower().split():
                token = word.strip(string.punctuation)
                if not token:
                    continue
                files = index.setdefault(token, [])
                if filename not in files:
                    files.append(filename)
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        text_words = set(self.tokenize(text))
        return sum(1 for word in set(self.tokenize(query)) if word in text_words)

    def tokenize(self, text):
        """
        Lowercases, strips punctuation and drops stopwords, so common words
        like "the" or "is" never count as evidence.
        """
        words = (w.strip(string.punctuation) for w in text.lower().split())
        return [w for w in words if w and w not in STOPWORDS]

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        # Guardrail 1: a query with no meaningful words has nothing to match
        query_words = set(self.tokenize(query))
        if not query_words:
            return []

        # Guardrail 2: a document must cover enough of the query's words
        min_score = max(1, math.ceil(MIN_MATCH_RATIO * len(query_words)))

        # Use the index to find candidate files containing any query word
        candidates = set()
        for word in query_words:
            candidates.update(self.index.get(word, []))

        results = []
        for filename, text in self.documents:
            if filename in candidates:
                score = self.score_document(query, text)
                if score >= min_score:
                    results.append((score, filename, text))

        results.sort(key=lambda r: r[0], reverse=True)

        # Guardrail 3: the chosen paragraph must itself match enough words
        snippets = []
        for _, filename, text in results[:top_k]:
            paragraph = self.best_paragraph(query, text)
            if self.score_document(query, paragraph) >= min_score:
                snippets.append((filename, paragraph))
        return snippets

    def best_paragraph(self, query, text):
        """
        Returns the single paragraph of text that best matches the query.
        A heading line is kept together with the paragraph that follows it.
        """
        paragraphs = []
        heading = ""
        for block in text.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if block.startswith("#") and "\n" not in block:
                heading = block + "\n"
                continue
            paragraphs.append(heading + block)
            heading = ""
        if heading:
            paragraphs.append(heading.strip())
        if not paragraphs:
            return text
        return max(paragraphs, key=lambda p: self.score_document(query, p))

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
