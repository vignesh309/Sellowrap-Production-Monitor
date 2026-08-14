import os
import sys
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter()

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    FRONTEND_DIR = os.path.join(PROJECT_ROOT, "Frontend")


def get_html_path(filename: str):
    filepath = os.path.join(FRONTEND_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return filepath


@router.get("/", response_class=HTMLResponse)
def login_page():
    return FileResponse(get_html_path("login.html"))

@router.get("/hub", response_class=HTMLResponse)
def hub_page():
    return FileResponse(get_html_path("hub.html"))

@router.get("/production-entry", response_class=HTMLResponse)
def production_entry_page():
    return FileResponse(get_html_path("production-entry.html"))


@router.get("/production-status", response_class=HTMLResponse)
def production_status_page():
    return FileResponse(get_html_path("productionstatus.html"))


@router.get("/production-entry-stage-1", response_class=HTMLResponse)
def production_entry_stage_1_page():
    return FileResponse(get_html_path("production_entry_stage_1.html"))

@router.get("/moulding-stage", response_class=HTMLResponse)
def moulding_stage_page():
    return FileResponse(get_html_path("moulding_stage.html"))


@router.get("/production-entry-stage-2", response_class=HTMLResponse)
def production_entry_stage_2_page():
    return FileResponse(get_html_path("production_entry_stage_2.html"))

@router.get("/machine_master", response_class=HTMLResponse)
def machine_master_page():
    return FileResponse(get_html_path("machine_master.html"))

@router.get("/part-master", response_class=HTMLResponse)
def part_master_page():
    return FileResponse(get_html_path("part_master.html"))

@router.get("/employee-master", response_class=HTMLResponse)
def employee_master_page():
    return FileResponse(get_html_path("employee_master.html"))

@router.get("/shortfall_reason_master", response_class=HTMLResponse)
def shortfall_reason_master_page():
    return FileResponse(get_html_path("shortfall_reason_master.html"))

@router.get("/rejection_reason_master", response_class=HTMLResponse)
def rejection_reason_master_page():
    return FileResponse(get_html_path("rejection_reason_master.html"))

@router.get("/batch-ledger-page", response_class=HTMLResponse)
def batch_ledger_page():
    return FileResponse(get_html_path("batch_ledger.html"))

@router.get("/production-hourly-status", response_class=HTMLResponse)
def production_hourly_status_page():
    return FileResponse(get_html_path("production_hourly_status.html"))

@router.get("/production-hourly-report", response_class=HTMLResponse)
def production_hourly_reports_page():
    return FileResponse(get_html_path("production_hourly_report.html"))

@router.get("/loss-analysis", response_class=HTMLResponse)
def loss_analysis_page():
    return FileResponse(get_html_path("loss_analysis.html"))

@router.get("/partwise-report", response_class=HTMLResponse)
def partwise_report_page():
    return FileResponse(get_html_path("partwise_report.html"))

@router.get("/shift-summary", response_class=HTMLResponse)
def shift_summary_page():
    return FileResponse(get_html_path("shift_summary.html"))

@router.get("/shift-summary-tvscreen", response_class=HTMLResponse)
def shift_summary_tvscreen_page():
    return FileResponse(get_html_path("shift_summary_tvscreen.html"))

@router.get("/oee-summary", response_class=HTMLResponse)
def oee_summary_page():
    return FileResponse(get_html_path("oee_summary.html"))

@router.get("/teep-summary", response_class=HTMLResponse)
def teep_summary_page():
    return FileResponse(get_html_path("teep_summary.html"))

@router.get("/teep-summary-idle-machines", response_class=HTMLResponse)
def teep_summary_idle_machines_page():
    return FileResponse(get_html_path("teep_summary_idle_machines.html"))

@router.get("/oeeteep-dashboard", response_class=HTMLResponse)
def oeeteep_dashboard_page():
    return FileResponse(get_html_path("oeeteep_dashboard.html"))

@router.get("/iot-summary", response_class=HTMLResponse)
def iot_summary_page():
    return FileResponse(get_html_path("iot_summary.html"))

@router.get("/iot-report", response_class=HTMLResponse)
def iot_report_page():
    return FileResponse(get_html_path("iot_report.html"))

@router.get("/detailed-shortfalls-report", response_class=HTMLResponse)
def detailed_shortfalls_report_page():
    return FileResponse(get_html_path("detailed_shortfalls_report.html"))

@router.get("/detailed-rejections-report", response_class=HTMLResponse)
def detailed_rejections_report_page():
    return FileResponse(get_html_path("detailed_rejections_report.html"))

@router.get("/non-hazardous-waste-generation-report", response_class=HTMLResponse)
def non_hazardous_waste_generation_report_page():
    return FileResponse(get_html_path("Plant_kpi_performance/non_hazardous_waste_generation_report.html"))