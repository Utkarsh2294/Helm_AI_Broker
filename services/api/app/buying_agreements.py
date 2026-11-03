from sqlalchemy import select
from app.db.policy_buying import BuyingAgreement
from app.db.models import uid, stamp


def accepted(db, buying, document):
    return db.scalar(
        select(BuyingAgreement).where(
            BuyingAgreement.consumer_key == buying.body["consumer_key"],
            BuyingAgreement.document_hash == document.content_hash,
        )
    )


def record_acceptance(db, buying, document):
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(
        insert(BuyingAgreement)
        .values(
            id=uid(),
            consumer_key=buying.body["consumer_key"],
            document_hash=document.content_hash,
            document_id=document.id,
            accepted_at=stamp(),
        )
        .on_conflict_do_nothing(index_elements=["consumer_key", "document_hash"])
    )
