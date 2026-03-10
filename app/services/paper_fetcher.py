import httpx

from app.config import settings
from app.models.schemas import PaperInfo


async def fetch_papers_by_code(paper_code: str, token: str = None) -> list[PaperInfo]:
    """
    Fetch all approved question papers from the existing PYQ API and
    filter by the given paper code.

    Args:
        paper_code: Subject paper code (e.g., "CSIT751")

    Returns:
        List of PaperInfo objects matching the paper code.

    Raises:
        httpx.HTTPStatusError: If the API request fails.
        ValueError: If no papers are found for the given code.
    """
    url = settings.PYQ_APPROVED_PAPERS_URL
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(timeout=settings.API_REQUEST_TIMEOUT) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    data = response.json()
    approved_papers = data.get("approvedPapers", [])

    # Filter papers by the requested paper code (case-insensitive)
    matching_papers = [
        PaperInfo(
            id=paper["_id"],
            paperName=paper["paperName"],
            paperCode=paper["paperCode"],
            department=paper["department"],
            programme=paper["programme"],
            month=paper["month"],
            year=paper["year"],
            fileUrl=paper["fileUrl"],
        )
        for paper in approved_papers
        if paper["paperCode"].upper() == paper_code.upper()
    ]

    if not matching_papers:
        raise ValueError(
            f"No approved question papers found for paper code: {paper_code}"
        )

    # Sort by year descending, then month
    matching_papers.sort(key=lambda p: (p.year, p.month), reverse=True)

    return matching_papers
