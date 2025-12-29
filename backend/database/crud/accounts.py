"""
CRUD operations for Account management
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from utils.time_utils import get_moscow_time
from database.models import Account, LeadsTechCabinet


def get_accounts(db: Session, user_id: Optional[int] = None) -> List[Account]:
    """Get all accounts for a user (or all accounts if user_id is None)"""
    if user_id is None:
        return db.query(Account).all()
    return db.query(Account).filter(Account.user_id == user_id).all()


def get_account_by_id(db: Session, user_id: int, account_id: int) -> Optional[Account]:
    """Get account by VK account ID for a user"""
    return db.query(Account).filter(
        Account.user_id == user_id,
        Account.account_id == account_id
    ).first()


def get_account_by_db_id(db: Session, user_id: int, db_id: int) -> Optional[Account]:
    """Get account by database ID for a user"""
    return db.query(Account).filter(
        Account.user_id == user_id,
        Account.id == db_id
    ).first()


def get_account_by_name(db: Session, user_id: int, name: str) -> Optional[Account]:
    """Get account by name for a user"""
    return db.query(Account).filter(
        Account.user_id == user_id,
        Account.name == name
    ).first()


def create_account(
    db: Session,
    user_id: int,
    account_id: int,
    name: str,
    api_token: str,
    client_id: int
) -> Account:
    """Create new account for a user"""
    db_account = Account(
        user_id=user_id,
        account_id=account_id,
        name=name,
        api_token=api_token,
        client_id=client_id
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def update_account(
    db: Session,
    user_id: int,
    account_id: int,
    name: Optional[str] = None,
    api_token: Optional[str] = None,
    client_id: Optional[int] = None,
    label: Optional[str] = None
) -> Optional[Account]:
    """Update account for a user"""
    account = get_account_by_id(db, user_id, account_id)
    if not account:
        return None

    if name is not None:
        account.name = name
    if api_token is not None:
        account.api_token = api_token
    if client_id is not None:
        account.client_id = client_id
    if label is not None:
        account.label = label if label else None  # Empty string -> None

    account.updated_at = get_moscow_time()
    db.commit()
    db.refresh(account)
    return account


def update_account_label(
    db: Session,
    user_id: int,
    account_db_id: int,
    label: Optional[str]
) -> Optional[Account]:
    """Update only the label field of an account by its database ID"""
    account = get_account_by_db_id(db, user_id, account_db_id)
    if not account:
        return None

    account.label = label if label else None  # Empty string -> None
    account.updated_at = get_moscow_time()
    db.commit()
    db.refresh(account)
    return account


def update_account_leadstech(
    db: Session,
    user_id: int,
    account_db_id: int,
    label: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Optional[Account]:
    """Update LeadsTech settings for an account"""
    account = get_account_by_db_id(db, user_id, account_db_id)
    if not account:
        return None

    if label is not None:
        account.label = label if label else None  # Empty string -> None
    if enabled is not None:
        account.leadstech_enabled = enabled

    account.updated_at = get_moscow_time()
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, user_id: int, account_id: int) -> bool:
    """Delete account for a user"""
    account = get_account_by_id(db, user_id, account_id)
    if not account:
        return False

    # Delete related LeadsTechCabinet records first
    db.query(LeadsTechCabinet).filter(LeadsTechCabinet.account_id == account.id).delete()

    # Now delete the account (other relations will cascade)
    db.delete(account)
    db.commit()
    return True
