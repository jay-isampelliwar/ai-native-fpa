"""The enum values stored in the conversation, run, profile and financial record tables."""

from enum import StrEnum


class ConversationStatus(StrEnum):

    """Where a conversation is in its life."""

    active = "active"
    archived = "archived"
    deleted = "deleted"


class MessageRole(StrEnum):

    """Who wrote a message."""

    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class MessageStatus(StrEnum):

    """Whether a message is still being written or has ended."""

    streaming = "streaming"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class RunStatus(StrEnum):

    """Where one agent run is between queued and its final state."""

    queued = "queued"
    running = "running"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


class ToolCallStatus(StrEnum):

    """Where one tool call is between requested and its final state."""

    requested = "requested"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    unknown = "unknown"



class RiskAppetite(StrEnum):

    """How much investment risk the user is comfortable with."""

    low = "low"
    medium = "medium"
    high = "high"


class FamilyRelation(StrEnum):

    """How a family member is related to the user."""

    spouse = "spouse"
    child = "child"
    parent = "parent"
    sibling = "sibling"
    other = "other"


class IncomeSourceType(StrEnum):

    """Where a regular income comes from."""

    salary = "salary"
    rent = "rent"
    business = "business"
    freelance = "freelance"
    pension = "pension"
    other = "other"


class PaymentFrequency(StrEnum):

    """How often an amount is paid or received."""

    monthly = "monthly"
    quarterly = "quarterly"
    half_yearly = "half_yearly"
    yearly = "yearly"


class ExpenseCategory(StrEnum):

    """What a regular expense is spent on."""

    rent = "rent"
    maintenance = "maintenance"
    groceries = "groceries"
    electricity = "electricity"
    water = "water"
    gas = "gas"
    mobile_internet = "mobile_internet"
    fuel = "fuel"
    public_transport = "public_transport"
    vehicle_maintenance = "vehicle_maintenance"
    education = "education"
    child_care = "child_care"
    elder_care = "elder_care"
    medicines = "medicines"
    doctor_visits = "doctor_visits"
    fitness = "fitness"
    smoking = "smoking"
    alcohol = "alcohol"
    dining_out = "dining_out"
    food_delivery = "food_delivery"
    clothing = "clothing"
    shopping = "shopping"
    electronics = "electronics"
    entertainment = "entertainment"
    subscriptions = "subscriptions"
    travel = "travel"
    household_help = "household_help"
    personal_care = "personal_care"
    pets = "pets"
    gifts = "gifts"
    donations = "donations"
    family_support = "family_support"
    gambling = "gambling"
    other = "other"


class TransactionDirection(StrEnum):

    """Whether a one-off amount came in or went out."""

    inflow = "inflow"
    outflow = "outflow"


class TransactionCategory(StrEnum):

    """What a one-off amount was for."""

    bonus = "bonus"
    gift = "gift"
    inheritance = "inheritance"
    asset_sale = "asset_sale"
    refund = "refund"
    purchase = "purchase"
    medical = "medical"
    travel = "travel"
    repair = "repair"
    other = "other"


class BankAccountType(StrEnum):

    """The kind of bank account."""

    savings = "savings"
    current = "current"
    salary = "salary"


class DepositType(StrEnum):

    """Whether a deposit is fixed or recurring."""

    fd = "fd"
    rd = "rd"


class RetirementAccountType(StrEnum):

    """The kind of retirement account."""

    epf = "epf"
    ppf = "ppf"
    nps = "nps"
    vpf = "vpf"


class PhysicalAssetType(StrEnum):

    """The kind of physical asset."""

    real_estate = "real_estate"
    gold = "gold"
    vehicle = "vehicle"
    other = "other"


class LoanType(StrEnum):

    """The kind of loan."""

    home = "home"
    car = "car"
    personal = "personal"
    education = "education"
    gold = "gold"
    other = "other"


class PolicyType(StrEnum):

    """The kind of insurance policy."""

    term = "term"
    health = "health"
    life = "life"
    ulip = "ulip"
    vehicle = "vehicle"
    other = "other"


class GoalType(StrEnum):

    """What a financial goal is for."""

    retirement = "retirement"
    education = "education"
    house = "house"
    marriage = "marriage"
    emergency = "emergency"
    vehicle = "vehicle"
    travel = "travel"
    other = "other"


class GoalStatus(StrEnum):

    """Where a goal is in its life."""

    active = "active"
    achieved = "achieved"
    dropped = "dropped"


class TaxRegime(StrEnum):

    """Which income tax regime the user files under."""

    old = "old"
    new = "new"


class AssumptionKey(StrEnum):

    """Which planning rate an assumption sets."""

    inflation = "inflation"
    education_inflation = "education_inflation"
    medical_inflation = "medical_inflation"
    equity_return = "equity_return"
    debt_return = "debt_return"
    gold_return = "gold_return"
    real_estate_return = "real_estate_return"
    salary_growth = "salary_growth"
    post_retirement_return = "post_retirement_return"



class GoalAssetTable(StrEnum):

    """Which kind of asset a goal allocation points at."""

    holdings = "holdings"
    fixed_deposits = "fixed_deposits"
    retirement_accounts = "retirement_accounts"
    bank_accounts = "bank_accounts"


class CoverageStatus(StrEnum):

    """Whether the user has given data for a section, has none, declined, or was not asked yet."""

    pending = "pending"
    provided = "provided"
    none = "none"
    declined = "declined"


class OutboxStatus(StrEnum):

    """Where one outbox event is between saved in Postgres and published to Redis."""

    pending = "pending"
    publishing = "publishing"
    published = "published"
    failed = "failed"
    dead_letter = "dead_letter"


class OutboxEventType(StrEnum):

    """Which deferred job an outbox event asks the memory worker to do."""

    memory_extract_requested = "memory.extract.requested"
    memory_summary_requested = "memory.summary.requested"
    memory_embed_requested = "memory.embed.requested"
    memory_cleanup_requested = "memory.cleanup.requested"


class MemoryStatus(StrEnum):

    """Where one memory is between first seen and removed."""

    candidate = "candidate"
    active = "active"
    superseded = "superseded"
    expired = "expired"
    rejected = "rejected"
    deleted = "deleted"


class MemoryEventType(StrEnum):

    """What happened to a memory in one history row."""

    created = "created"
    updated = "updated"
    confirmed = "confirmed"
    superseded = "superseded"
    rejected = "rejected"
    expired = "expired"
    deleted = "deleted"


class MemoryActorType(StrEnum):

    """Who made a change to a memory."""

    user = "user"
    agent = "agent"
    system = "system"


ACTIVE_RUN_STATUSES = (RunStatus.queued, RunStatus.running, RunStatus.cancel_requested)
