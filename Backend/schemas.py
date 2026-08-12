from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal

# ==========================================
# MASTER DATA SCHEMAS (Part / Machine Manager)
# ==========================================

class MachinePayload(BaseModel):
    machine_code: str
    machine_name: str
    is_active: bool
    machine_process: str  # 🚨 NEW: Added process mapping

class UnifiedRouteItem(BaseModel):
    sequence: int
    process_name: str
    mold_no: Optional[str] = "-"
    mold_name: Optional[str] = "-"
    # Updated to Decimal to accept values like 0.5
    cavities: Decimal = Decimal('1.00')
    active_cavities: Decimal = Decimal('1.00')
    hourly_target: int = 0 
    target_temp: float = 0.0
    target_pressure: float = 0.0
    target_setting: float = 0.0

class ProcessItem(BaseModel):
    sequence: int
    process_name: str
    erp_code: str = ""
    hourly_target: int = 0        # 🚨 NEW
    target_temp: float = 0.0      
    target_pressure: float = 0.0  
    target_setting: float = 0.0

class PartMasterPayload(BaseModel):
    part_no: str
    part_name: str
    customer_name: Optional[str] = "" 
    routing: List[UnifiedRouteItem]

# ==========================================
# PRODUCTION ENTRY SCHEMAS (Stage 1 Hourly)
# ==========================================

class BreakupItem(BaseModel):
    reason: str
    qty: int

class RejectionDetail(BaseModel):
    reason: str
    qty: int

class Stage1BlockSubmit(BaseModel):
    batch_id: str
    internal_batch_number: str
    production_date: str
    shift: str
    start_time: str    
    end_time: str      
    machine_code: str
    mould_code: str
    part_number: str
    operator_code: str 
    supervisor_code: str
    target_shots: int
    actual_shots: int
    
    # 🚨 FIXED: Changed from int to float to support 0.5 cavities!
    active_cavities: float 
    
    ok_parts: int
    ng_parts: int
    actual_temp: float
    actual_pressure: float
    actual_setting: float
    rejections: List[RejectionDetail] 
    shortfalls: List[BreakupItem]
    is_no_plan: bool = False  

class FinalizeBatchPayload(BaseModel):
    batch_id: str
    sequence_no: int
    process_name: str
    input_qty: int
    ok_qty: int
    ng_qty: int
    emp_code: str
    is_outsourced: bool
    fg_part_number: str
    remarks: Optional[str] = ""

class ActiveMachineState(BaseModel):
    machine_code: str
    internal_batch_number: str
    part_number: str
    mould_code: str
    operator_code: str
    supervisor_code: str

# ==========================================
# Employee Master Schema
# ==========================================

class EmployeeModel(BaseModel):
    emp_code: str
    full_name: str
    job_role: str
    username: str
    password_hash: str
    is_active: bool

class OTPVerifyModel(BaseModel):
    otp: str

class RejectionReasonPayload(BaseModel):
    reason_code: str
    reason_name: str
    category: str
    oee_impact: str
    is_active: bool

class ShortfallReasonPayload(BaseModel):
    reason_code: str
    reason_name: str
    category: str
    is_active: bool