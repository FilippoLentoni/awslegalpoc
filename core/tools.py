import logging
import os

import boto3
from strands.tools import tool

from core.config import BEDROCK_KB_ID, BEDROCK_REGION

logger = logging.getLogger(__name__)

_bedrock_agent_runtime_client = None


def _get_client():
    global _bedrock_agent_runtime_client
    if _bedrock_agent_runtime_client is None:
        region = BEDROCK_REGION or os.getenv("AWS_REGION", "us-east-2")
        _bedrock_agent_runtime_client = boto3.client(
            "bedrock-agent-runtime", region_name=region
        )
    return _bedrock_agent_runtime_client


@tool
def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """Cerca nella base documentale informazioni rilevanti su diritto notarile italiano,
    regime patrimoniale della famiglia, successioni e donazioni, contratti e obbligazioni.

    Utilizza questo strumento quando l'utente pone una domanda che possa essere
    risolta consultando la documentazione giuridica disponibile: manuali, trattati,
    riferimenti normativi e dottrinali.

    Args:
        query: La query di ricerca per trovare documenti rilevanti
        max_results: Numero massimo di risultati da restituire (default: 5)

    Returns:
        Una stringa formattata contenente i risultati della ricerca con citazione delle fonti
    """
    knowledge_base_id = os.environ.get("KNOWLEDGE_BASE_ID") or BEDROCK_KB_ID

    if not knowledge_base_id:
        return (
            "Knowledge base search is not available. "
            "The KNOWLEDGE_BASE_ID environment variable is not set."
        )

    client = _get_client()

    try:
        response = client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = response.get("retrievalResults", [])

        if not results:
            return f"No results found for query: {query}"

        formatted_results = []
        for i, result in enumerate(results, 1):
            content = result.get("content", {}).get("text", "No content")
            score = result.get("score", 0)
            location = result.get("location", {})
            source_type = location.get("type", "UNKNOWN")

            if source_type == "S3":
                source = location.get("s3Location", {}).get("uri", "Unknown")
            else:
                source = f"Source type: {source_type}"

            text = f"Result {i} (Relevance: {score:.2f})\n"
            text += f"Source: {source}\n"
            if len(content) > 800:
                content = content[:800] + "..."
            text += f"Content: {content}\n"
            formatted_results.append(text)

        return "\n---\n".join(formatted_results)

    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return f"Error searching knowledge base: {str(e)}"


SYSTEM_PROMPT = """Sei un assistente giuridico specializzato in diritto notarile italiano. Il tuo compito e' fornire risposte accurate e dettagliate su questioni di diritto civile italiano, con particolare competenza in:

- Regime patrimoniale della famiglia (comunione e separazione dei beni, convenzioni matrimoniali, fondo patrimoniale)
- Successioni e donazioni (successione legittima, testamentaria, patti successori, donazioni)
- Il contratto in generale (formazione, validita', efficacia, risoluzione, rescissione)
- Le obbligazioni (fonti, adempimento, inadempimento, estinzione)

Regole operative:
1. Rispondi SEMPRE in italiano
2. Utilizza SEMPRE lo strumento search_knowledge_base per cercare informazioni pertinenti prima di rispondere
3. Cita le fonti specifiche: articoli del Codice Civile, riferimenti dottrinali (autore, opera) quando disponibili
4. Se la knowledge base non contiene informazioni sufficienti, dichiaralo esplicitamente e NON inventare riferimenti normativi o dottrinali
5. Struttura le risposte in modo chiaro: principio generale, eccezioni, riferimenti normativi
6. Quando possibile, distingui tra orientamento dottrinale maggioritario e minoritario
7. Usa un linguaggio tecnico-giuridico appropriato ma comprensibile

Hai accesso a:
1. search_knowledge_base() - Cerca nella base documentale contenente manuali di diritto notarile, trattati e capitoli sul regime patrimoniale della famiglia, successioni e donazioni, contratti e obbligazioni.

Utilizza sempre lo strumento search_knowledge_base per trovare informazioni accurate e aggiornate dalla documentazione. Non fare supposizioni o inventare contenuti giuridici."""
