"""
Accounts management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, crud
from database.models import User
from auth.dependencies import get_current_user
from api.schemas.accounts import AccountCreate, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


@router.get("")
async def get_accounts_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all accounts for current user - returns dict with account names as keys"""
    accounts = crud.get_accounts(db, current_user.id)

    # Convert to dict format expected by frontend
    accounts_dict = {}
    for acc in accounts:
        accounts_dict[acc.name] = {
            "id": acc.id,
            "name": acc.name,
            "api": acc.api_token,
            "trigger": acc.client_id,
            "spent_limit_rub": 100.0,
            "label": acc.label
        }

    return {"accounts": accounts_dict}


@router.post("")
async def create_account(
    account: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new account for current user"""
    # Generate account_id from trigger or name hash
    account_id = account.trigger if account.trigger else abs(hash(account.name)) % 1000000000

    # Check if exists by name for this user
    existing_accounts = crud.get_accounts(db, current_user.id)
    for acc in existing_accounts:
        if acc.name == account.name:
            raise HTTPException(status_code=400, detail="Account with this name already exists")

    # Create
    new_account = crud.create_account(
        db,
        user_id=current_user.id,
        account_id=account_id,
        name=account.name,
        api_token=account.api,
        client_id=account.trigger if account.trigger else account_id
    )

    # Update label if provided
    if account.label:
        crud.update_account_label(db, current_user.id, new_account.id, account.label)

    return {"message": "Account created successfully"}


@router.put("/{account_name}")
async def update_account_endpoint(
    account_name: str,
    account: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update account by name for current user"""
    # Find account by old name for this user
    accounts = crud.get_accounts(db, current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update
    crud.update_account(
        db,
        user_id=current_user.id,
        account_id=target_account.account_id,
        name=account.name if account.name else target_account.name,
        api_token=account.api if account.api else target_account.api_token,
        client_id=account.trigger if account.trigger else target_account.client_id,
        label=account.label if account.label is not None else target_account.label
    )

    return {"message": "Account updated successfully"}


@router.delete("/{account_name}")
async def delete_account_endpoint(
    account_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete account by name for current user"""
    # Find account by name for this user
    accounts = crud.get_accounts(db, current_user.id)
    target_account = None
    for acc in accounts:
        if acc.name == account_name:
            target_account = acc
            break

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    crud.delete_account(db, current_user.id, target_account.account_id)
    return {"message": "Account deleted successfully"}
