import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { UserSettings } from "@/lib/types";

// Mock hooks
const mockUseSettings = vi.fn();
const mockUseAuthStatus = vi.fn();
vi.mock("@/lib/hooks", () => ({
  useSettings: () => mockUseSettings(),
  useAuthStatus: () => mockUseAuthStatus(),
}));

// Mock API
const mockUpdateSettings = vi.fn();
const mockDisconnect = vi.fn();
vi.mock("@/lib/api", () => ({
  updateSettings: (...args: unknown[]) => mockUpdateSettings(...args),
  disconnect: () => mockDisconnect(),
}));

// Mock SWR mutate
vi.mock("swr", async () => {
  const actual = await vi.importActual("swr");
  return { ...actual, mutate: vi.fn() };
});

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
}));

import SettingsPage from "@/app/settings/page";

const MOCK_SETTINGS: UserSettings = {
  trading_mode: "manual",
  max_trade_size_cents: 100,
  daily_loss_limit_cents: 1000,
  max_daily_exposure_cents: 2500,
  min_ev_threshold: 0.05,
  cooldown_per_loss_minutes: 60,
  consecutive_loss_limit: 3,
  active_cities: ["NYC", "CHI", "MIA", "AUS"],
  notifications_enabled: true,
};

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Suppress confirm dialog
    vi.spyOn(window, "confirm").mockReturnValue(false);
    // Default auth status mock
    mockUseAuthStatus.mockReturnValue({
      data: {
        authenticated: true,
        user_id: "test-user",
        demo_mode: true,
        key_id_prefix: "abc123...",
      },
      error: undefined,
      isLoading: false,
    });
  });

  it("shows loading state", () => {
    mockUseSettings.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
    });

    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    const skeletons = document.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state", () => {
    mockUseSettings.mockReturnValue({
      data: undefined,
      error: new Error("Failed to load"),
      isLoading: false,
    });

    render(<SettingsPage />);
    expect(screen.getByText("Failed to load")).toBeInTheDocument();
  });

  it("renders settings form with current values", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);

    // Trading mode
    expect(screen.getByText("Trading Mode")).toBeInTheDocument();
    expect(screen.getByText("manual")).toBeInTheDocument();
    expect(screen.getByText("auto")).toBeInTheDocument();

    // Risk limits section
    expect(screen.getByText("Risk Limits")).toBeInTheDocument();
    expect(screen.getByText("$1.00")).toBeInTheDocument(); // max trade size
    expect(screen.getByText("$10.00")).toBeInTheDocument(); // daily loss limit

    // Cities
    expect(screen.getByText("Active Cities")).toBeInTheDocument();
    expect(screen.getByText("NYC")).toBeInTheDocument();
    expect(screen.getByText("CHI")).toBeInTheDocument();

    // Notifications
    expect(screen.getByText("Notifications")).toBeInTheDocument();

    // Save button
    expect(screen.getByText("Save Settings")).toBeInTheDocument();
  });

  it("toggles trading mode", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);

    const autoButton = screen.getByText("auto");
    fireEvent.click(autoButton);

    // Check the auto button gets the active style
    expect(autoButton.className).toContain("bg-boz-primary");
  });

  it("toggles city selection", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);

    // NYC should be active initially
    const nycButton = screen.getByText("NYC");
    expect(nycButton.className).toContain("bg-boz-primary");

    // Click to deselect
    fireEvent.click(nycButton);
    expect(nycButton.className).not.toContain("bg-boz-primary");

    // Click to reselect
    fireEvent.click(nycButton);
    expect(nycButton.className).toContain("bg-boz-primary");
  });

  it("calls updateSettings on save", async () => {
    mockUpdateSettings.mockResolvedValue(MOCK_SETTINGS);
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);

    fireEvent.click(screen.getByText("Save Settings"));

    await waitFor(() => {
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          trading_mode: "manual",
          max_trade_size_cents: 100,
          active_cities: ["NYC", "CHI", "MIA", "AUS"],
        })
      );
    });
  });

  it("shows save success message", async () => {
    mockUpdateSettings.mockResolvedValue(MOCK_SETTINGS);
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);
    fireEvent.click(screen.getByText("Save Settings"));

    await waitFor(() => {
      expect(screen.getByText("Settings saved!")).toBeInTheDocument();
    });
  });

  it("shows save error message", async () => {
    mockUpdateSettings.mockRejectedValue(new Error("Save failed"));
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);
    fireEvent.click(screen.getByText("Save Settings"));

    await waitFor(() => {
      expect(screen.getByText("Save failed")).toBeInTheDocument();
    });
  });

  it("has disconnect button", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);
    expect(
      screen.getByText("Disconnect Kalshi Account")
    ).toBeInTheDocument();
  });

  it("shows connection status with demo badge", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);
    expect(screen.getByText("Connection Status")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("DEMO")).toBeInTheDocument();
    expect(screen.getByText("Key: abc123...")).toBeInTheDocument();
  });

  it("shows live badge when not in demo mode", () => {
    mockUseAuthStatus.mockReturnValue({
      data: {
        authenticated: true,
        user_id: "test-user",
        demo_mode: false,
        key_id_prefix: "xyz789...",
      },
      error: undefined,
      isLoading: false,
    });
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("Key: xyz789...")).toBeInTheDocument();
  });

  it("slider changes update display values", () => {
    mockUseSettings.mockReturnValue({
      data: MOCK_SETTINGS,
      error: undefined,
      isLoading: false,
    });

    render(<SettingsPage />);

    // Find max trade size slider by its associated label text
    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBeGreaterThan(0);

    // Change the first slider (max trade size)
    fireEvent.change(sliders[0], { target: { value: "200" } });
    expect(screen.getByText("$2.00")).toBeInTheDocument();
  });
});
