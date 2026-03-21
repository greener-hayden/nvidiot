"""Pydantic request/response models."""

from pydantic import BaseModel, Field


class GPUInfo(BaseModel):
    name: str
    temperature_c: int | None = None


class SettingInfo(BaseModel):
    settingId: int
    settingIdHex: str
    settingName: str
    settingType: int
    currentValue: int | str
    isPredefined: bool


class AppInfo(BaseModel):
    appName: str
    userFriendlyName: str
    isPredefined: bool


class ProfileSummary(BaseModel):
    profileName: str
    isPredefined: bool
    numOfApps: int
    numOfSettings: int


class ProfileDetail(ProfileSummary):
    settings: list[SettingInfo] = []
    applications: list[AppInfo] = []


class BaseProfileDetail(BaseModel):
    profileName: str
    isPredefined: bool
    numOfSettings: int
    settings: list[SettingInfo] = []


class SetSettingRequest(BaseModel):
    value: int


class CreateProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=2000)


class AppRequest(BaseModel):
    exe: str = Field(min_length=1, max_length=260)


class SettingIdEntry(BaseModel):
    id: int
    idHex: str
    name: str


class DisplayInfo(BaseModel):
    width: int
    height: int
    refresh: int
    saturation: int


class SetSaturationRequest(BaseModel):
    level: int = Field(ge=0, le=100)


class SetResolutionRequest(BaseModel):
    width: int = Field(ge=640, le=15360)
    height: int = Field(ge=480, le=8640)
    refresh: int | None = Field(default=None, ge=24, le=600)
    stretch: bool = True


class GamingPresetRequest(BaseModel):
    width: int = Field(ge=640, le=15360)
    height: int = Field(ge=480, le=8640)
    saturation: int = Field(default=90, ge=0, le=100)
    refresh: int | None = Field(default=None, ge=24, le=600)
    stretch: bool = True


class DesktopPresetRequest(BaseModel):
    saturation: int = Field(default=50, ge=0, le=100)
