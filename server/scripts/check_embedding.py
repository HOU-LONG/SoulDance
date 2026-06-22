import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings
from backend.app.data_loader import load_products
from backend.app.embedding_retriever import EmbeddingRetriever


def main() -> None:
    settings = get_settings()
    products = load_products(settings.dataset_path)
    retriever = EmbeddingRetriever(
        products,
        settings.embedding_path,
        settings.embedding_device,
        use_embedding=settings.use_embedding,
    )
    results = retriever.search("推荐防晒霜 不含酒精 非日系", top_k=3)
    print(
        {
            "model_path": str(settings.embedding_path),
            "embedding_loaded": retriever.model is not None,
            "product_count": len(products),
            "top_results": [
                {
                    "product_id": product.product_id,
                    "title": product.title,
                    "score": round(score, 4),
                }
                for product, score in results
            ],
        }
    )


if __name__ == "__main__":
    main()
