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
    awaiting_approval = "awaiting_approval"
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
    awaiting_approval = "awaiting_approval"
    rejected = "rejected"



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


class ApprovalStatus(StrEnum):

    """Where one approval request is between shown to the user and decided."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    cancelled = "cancelled"


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


ACTIVE_RUN_STATUSES = (
    RunStatus.queued,
    RunStatus.running,
    RunStatus.cancel_requested,
    RunStatus.awaiting_approval,
    )


class StockExchange(StrEnum):

    """The exchange a stock is listed on."""

    nse = "nse"
    bse = "bse"


class MarketCapType(StrEnum):

    """SEBI's large, mid or small cap bucket for a stock."""

    large = "large"
    mid = "mid"
    small = "small"


class StockSector(StrEnum):

    """The sector a listed company belongs to."""

    financial_services = "financial_services"
    information_technology = "information_technology"
    oil_gas_energy = "oil_gas_energy"
    fmcg = "fmcg"
    automobile = "automobile"
    healthcare = "healthcare"
    metals_mining = "metals_mining"
    capital_goods = "capital_goods"
    construction = "construction"
    consumer_durables = "consumer_durables"
    consumer_services = "consumer_services"
    telecom = "telecom"
    power = "power"
    realty = "realty"
    chemicals = "chemicals"
    textiles = "textiles"
    media = "media"
    services = "services"
    diversified = "diversified"
    other = "other"


class FundCategory(StrEnum):

    """The broad kind of a mutual fund scheme."""

    equity = "equity"
    debt = "debt"
    hybrid = "hybrid"
    gold = "gold"
    other = "other"


class FundSubCategory(StrEnum):

    """The SEBI category of a mutual fund scheme."""

    large_cap = "large_cap"
    mid_cap = "mid_cap"
    small_cap = "small_cap"
    large_and_mid_cap = "large_and_mid_cap"
    multi_cap = "multi_cap"
    flexi_cap = "flexi_cap"
    focused = "focused"
    value = "value"
    contra = "contra"
    dividend_yield = "dividend_yield"
    elss = "elss"
    sectoral_thematic = "sectoral_thematic"
    index_fund = "index_fund"
    liquid = "liquid"
    overnight = "overnight"
    ultra_short_duration = "ultra_short_duration"
    low_duration = "low_duration"
    money_market = "money_market"
    short_duration = "short_duration"
    medium_duration = "medium_duration"
    long_duration = "long_duration"
    dynamic_bond = "dynamic_bond"
    corporate_bond = "corporate_bond"
    credit_risk = "credit_risk"
    banking_and_psu = "banking_and_psu"
    gilt = "gilt"
    floater = "floater"
    aggressive_hybrid = "aggressive_hybrid"
    conservative_hybrid = "conservative_hybrid"
    balanced_advantage = "balanced_advantage"
    multi_asset = "multi_asset"
    arbitrage = "arbitrage"
    equity_savings = "equity_savings"
    fund_of_funds = "fund_of_funds"
    solution_oriented = "solution_oriented"
    other = "other"


class FundPlanType(StrEnum):

    """Whether a fund plan is bought direct or through a distributor."""

    direct = "direct"
    regular = "regular"


class FundOptionType(StrEnum):

    """Whether a fund plan keeps its gains or pays them out."""

    growth = "growth"
    idcw = "idcw"


class HoldingAssetClass(StrEnum):

    """What one line of a fund's portfolio is: shares, bonds, fund units or cash."""

    equity = "equity"
    debt = "debt"
    fund_units = "fund_units"
    cash_and_other = "cash_and_other"


class HoldingAssetType(StrEnum):

    """Whether a user's holding is a stock or a mutual fund."""

    stock = "stock"
    mutual_fund = "mutual_fund"


class DocumentStatus(StrEnum):

    """Where one uploaded file is between uploaded and its rows written or rejected."""

    uploaded = "uploaded"
    parsed = "parsed"
    imported = "imported"
    rejected = "rejected"
    failed = "failed"


class ImportRowAction(StrEnum):

    """What approving one parsed row would do to the user's records."""

    create = "create"
    update = "update"
    no_change = "no_change"


class ImportRowStatus(StrEnum):

    """Where one parsed row is between shown in the preview and written, rejected or undone."""

    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    written = "written"
    failed = "failed"
    undone = "undone"
