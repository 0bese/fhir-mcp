"""
fhir_tools.py
A minimal FastMCP-based server that exposes common FHIR REST calls
via the async FHIRClient wrapper.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from fastmcp import FastMCP
from pydantic import Field
from typing_extensions import Annotated

# ------------------------------------------------------------------ #
# Logging
# ------------------------------------------------------------------ #

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# FHIR REST Client
# ------------------------------------------------------------------ #

class FHIRClient:
    """
    Thin async wrapper around a FHIR REST endpoint.
    Supports bearer tokens, timeouts, and very light validation.
    """

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    # ------------------ Internal helpers ------------------ #
    def _headers(self) -> Dict[str, str]:
        hdr = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self.auth_token:
            hdr["Authorization"] = f"Bearer {self.auth_token}"
        return hdr

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        try:
            logger.debug("FHIR %s %s", method, url)
            r = await self._client.request(method, url, headers=self._headers(), **kwargs)
            if r.status_code == 404:
                return self._operation_outcome("not-found", "Resource not found")
            if r.status_code == 401:
                return self._operation_outcome("security", "Authentication required")
            if r.status_code == 403:
                return self._operation_outcome("forbidden", "Access forbidden")
            r.raise_for_status()
            try:
                return r.json()
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON from %s: %s", url, e)
                return self._operation_outcome("invalid", f"Invalid JSON: {e}")
        except httpx.TimeoutException:
            logger.warning("Request timed out: %s", url)
            return self._operation_outcome("timeout", "Request timed out")
        except httpx.HTTPError as e:
            logger.error("HTTP error on %s: %s", url, e)
            return self._operation_outcome("exception", f"HTTP error: {e}")
        except Exception as e:
            logger.exception("Unexpected error on %s: %s", url, e)
            return self._operation_outcome("exception", f"Unexpected error: {e}")

    @staticmethod
    def _operation_outcome(code: str, text: str) -> Dict[str, Any]:
        return {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": code,
                    "details": {"text": text},
                }
            ],
        }

    # ------------------ CRUD / search ------------------ #
    async def get_patient(self, patient_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"Patient/{patient_id}")

    async def search_patients(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "Patient", params=params)

    async def search_observations(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "Observation", params=params)

    async def search_conditions(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "Condition", params=params)

    async def search_medication_requests(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "MedicationRequest", params=params)

    async def search_diagnostic_reports(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "DiagnosticReport", params=params)

    async def search_care_plans(self, **params) -> Dict[str, Any]:
        return await self._request("GET", "CarePlan", params=params)

    async def get_capability_statement(self) -> Dict[str, Any]:
        return await self._request("GET", "metadata")

    # ------------------ Data-quality helpers ------------------ #
    async def assess_data_quality(
        self, resource_type: Optional[str] = None
    ) -> Dict[str, Any]:
        assessment = {
            "server_url": self.base_url,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "resource_assessments": {},
        }
        test_types = (
            [resource_type]
            if resource_type
            else ["Patient", "Observation", "Condition", "MedicationRequest"]
        )

        for rt in test_types:
            try:
                bundle = await self._request("GET", rt, params={"_count": 10})
                validation = self._validate_fhir_response(bundle)
                assessment["resource_assessments"][rt] = {
                    "accessible": validation["is_valid"],
                    "total_available": validation.get("data_quality", {}).get(
                        "total_resources", 0
                    ),
                    "issues": validation["issues"],
                    "data_quality_score": self._calculate_quality_score(validation),
                }
            except Exception as e:
                assessment["resource_assessments"][rt] = {
                    "accessible": False,
                    "error": str(e),
                    "data_quality_score": 0.0,
                }
        return assessment

    # ------------------ Validation / scoring ------------------ #
    def _validate_fhir_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        validation = {
            "is_valid": True,
            "issues": [],
            "data_quality": {},
            "resource_type": response.get("resourceType", "Unknown"),
        }

        if response.get("resourceType") == "OperationOutcome":
            validation["is_valid"] = False
            for issue in response.get("issue", []):
                validation["issues"].append(
                    {
                        "severity": issue.get("severity", "unknown"),
                        "code": issue.get("code", "unknown"),
                        "details": issue.get("details", {}).get("text", "No details"),
                    }
                )
            return validation

        if response.get("resourceType") == "Bundle":
            entries = response.get("entry", [])
            total = response.get("total", 0)
            validation["data_quality"] = {
                "total_resources": total,
                "returned_resources": len(entries),
                "has_next_page": any(
                    link.get("relation") == "next"
                    for link in response.get("link", [])
                ),
                "resource_types": list(
                    {
                        entry.get("resource", {}).get("resourceType")
                        for entry in entries
                        if "resource" in entry
                    }
                ),
            }

        return validation

    def _calculate_quality_score(self, validation: Dict[str, Any]) -> float:
        if not validation["is_valid"]:
            return 0.0
        score = 100.0
        for issue in validation["issues"]:
            if issue["severity"] == "error":
                score -= 30
            elif issue["severity"] == "warning":
                score -= 10
        if validation.get("data_quality", {}).get("total_resources", 0) == 0:
            score -= 50
        return max(0.0, score)

    # ------------------ Context manager ------------------ #
    async def __aenter__(self) -> FHIRClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

# ------------------------------------------------------------------ #
# FastMCP Server
# ------------------------------------------------------------------ #

mcp = FastMCP("fhir-mcp")

# ---------- Patients ----------
@mcp.tool
async def get_patient(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient_id: Annotated[str, Field(description="FHIR Patient ID")],
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Retrieve a single Patient resource by ID."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        return await client.get_patient(patient_id)

@mcp.tool
async def search_patients(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    name: Annotated[Optional[str], Field(description="Given or family name to match")] = None,
    family: Annotated[Optional[str], Field(description="Family name only")] = None,
    _count: Annotated[int, Field(ge=1, le=1000, description="Max results per page")] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """
    Search Patient resources.
    Leave all filters empty to list the first N patients.
    """
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if name:
            params["name"] = name
        if family:
            params["family"] = family
        return await client.search_patients(**params)

# ---------- Observations ----------
@mcp.tool
async def search_observations(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient: Annotated[Optional[str], Field(description="Patient ID to scope results")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Query Observation resources (vitals, labs, etc.)."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if patient:
            params["patient"] = patient
        return await client.search_observations(**params)

# ---------- Conditions ----------
@mcp.tool
async def search_conditions(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient: Annotated[Optional[str], Field(description="Limit to a single patient")] = None,
    code: Annotated[Optional[str], Field(description="SNOMED or ICD-10 code")] = None,
    clinical_status: Annotated[Optional[str], Field(description="active | resolved | inactive")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Find Condition resources (diagnoses)."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if patient:
            params["patient"] = patient
        if code:
            params["code"] = code
        if clinical_status:
            params["clinical-status"] = clinical_status
        return await client.search_conditions(**params)

# ---------- MedicationRequest ----------
@mcp.tool
async def search_medication_requests(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient: Annotated[Optional[str], Field(description="Patient ID")] = None,
    status: Annotated[Optional[str], Field(description="active | completed | stopped | on-hold")] = None,
    intent: Annotated[Optional[str], Field(description="order | plan | proposal")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Query prescribed/planned medications."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if patient:
            params["patient"] = patient
        if status:
            params["status"] = status
        if intent:
            params["intent"] = intent
        return await client.search_medication_requests(**params)

# ---------- DiagnosticReport ----------
@mcp.tool
async def search_diagnostic_reports(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient: Annotated[Optional[str], Field(description="Patient ID")] = None,
    status: Annotated[Optional[str], Field(description="final | preliminary | amended")] = None,
    category: Annotated[Optional[str], Field(description="LAB | RAD | etc.")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Query lab results, imaging reports, etc."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if patient:
            params["patient"] = patient
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        return await client.search_diagnostic_reports(**params)

# ---------- CarePlan ----------
@mcp.tool
async def search_care_plans(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    patient: Annotated[Optional[str], Field(description="Patient ID")] = None,
    status: Annotated[Optional[str], Field(description="active | completed | cancelled | draft")] = None,
    category: Annotated[Optional[str], Field(description="e.g., diabetes-management | encounter")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 10,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Find care plans (treatment plans, pathways)."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if patient:
            params["patient"] = patient
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        return await client.search_care_plans(**params)

# ---------- Utility ----------
@mcp.tool
async def find_patients_with_conditions(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    code: Annotated[Optional[str], Field(description="Condition code to filter on")] = None,
    _count: Annotated[int, Field(ge=1, le=1000)] = 100,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> list[str]:
    """
    Return distinct Patient IDs referenced by Condition resources.
    Useful when Patient records are missing but Conditions exist.
    """
    async with FHIRClient(fhir_base_url, auth_token) as client:
        params = {"_count": _count}
        if code:
            params["code"] = code
        bundle = await client.search_conditions(**params)
        patient_ids = {
            ref.split("/")[-1]
            for entry in bundle.get("entry", [])
            if (ref := entry.get("resource", {}).get("subject", {}).get("reference", ""))
            and ref.startswith("Patient/")
        }
        return sorted(patient_ids)

@mcp.tool
async def assess_data_quality(
    fhir_base_url: Annotated[str, Field(description="FHIR server base URL")],
    resource_type: Annotated[Optional[str], Field(description="Limit scan to one resource type")] = None,
    auth_token: Annotated[Optional[str], Field(description="Bearer token for authentication")] = None,
) -> dict:
    """Run a quality assessment across (or for) resource types."""
    async with FHIRClient(fhir_base_url, auth_token) as client:
        return await client.assess_data_quality(resource_type)

