import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

// Mock API
vi.mock("@/lib/api", () => ({
  validateCredentials: vi.fn(),
}));

import { validateCredentials } from "@/lib/api";
import OnboardingPage from "@/app/onboarding/page";

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders welcome step initially", () => {
    render(<OnboardingPage />);
    expect(
      screen.getByText("Welcome to Boz Weather Trader")
    ).toBeInTheDocument();
    expect(screen.getByText("Get Started")).toBeInTheDocument();
  });

  it("navigates to instructions on Get Started click", () => {
    render(<OnboardingPage />);
    fireEvent.click(screen.getByText("Get Started"));
    expect(screen.getByText("Connect to Kalshi")).toBeInTheDocument();
  });

  it("navigates through steps to API key input", () => {
    render(<OnboardingPage />);

    // Step 1 → 2
    fireEvent.click(screen.getByText("Get Started"));
    // Step 2 → 3
    fireEvent.click(screen.getByText("Continue"));

    expect(screen.getByText("Enter API Credentials")).toBeInTheDocument();
    expect(screen.getByLabelText("Key ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Private Key (PEM)")).toBeInTheDocument();
  });

  it("disables validate button when fields are empty", () => {
    render(<OnboardingPage />);
    fireEvent.click(screen.getByText("Get Started"));
    fireEvent.click(screen.getByText("Continue"));

    const validateBtn = screen.getByText("Validate");
    expect(validateBtn.closest("button")).toBeDisabled();
  });

  it("enables validate button when fields are filled", () => {
    render(<OnboardingPage />);
    fireEvent.click(screen.getByText("Get Started"));
    fireEvent.click(screen.getByText("Continue"));

    fireEvent.change(screen.getByLabelText("Key ID"), {
      target: { value: "test-key-id" },
    });
    fireEvent.change(screen.getByLabelText("Private Key (PEM)"), {
      target: { value: "test-private-key-pem" },
    });

    const validateBtn = screen.getByText("Validate");
    expect(validateBtn.closest("button")).not.toBeDisabled();
  });

  it("shows validation error on failed validate", async () => {
    const mockValidate = validateCredentials as ReturnType<typeof vi.fn>;
    mockValidate.mockRejectedValue(new Error("Invalid credentials"));

    render(<OnboardingPage />);
    fireEvent.click(screen.getByText("Get Started"));
    fireEvent.click(screen.getByText("Continue"));

    fireEvent.change(screen.getByLabelText("Key ID"), {
      target: { value: "bad-key" },
    });
    fireEvent.change(screen.getByLabelText("Private Key (PEM)"), {
      target: { value: "bad-pem" },
    });

    fireEvent.click(screen.getByText("Validate"));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });

  it("advances to success step on valid credentials", async () => {
    const mockValidate = validateCredentials as ReturnType<typeof vi.fn>;
    mockValidate.mockResolvedValue({ valid: true, balance_cents: 5000 });

    render(<OnboardingPage />);
    fireEvent.click(screen.getByText("Get Started"));
    fireEvent.click(screen.getByText("Continue"));

    fireEvent.change(screen.getByLabelText("Key ID"), {
      target: { value: "good-key" },
    });
    fireEvent.change(screen.getByLabelText("Private Key (PEM)"), {
      target: { value: "good-pem" },
    });

    fireEvent.click(screen.getByText("Validate"));

    await waitFor(() => {
      expect(
        screen.getByText("Connected Successfully!")
      ).toBeInTheDocument();
      expect(screen.getByText("Account Balance: $50.00")).toBeInTheDocument();
    });
  });

  it("shows risk disclaimer step", async () => {
    const mockValidate = validateCredentials as ReturnType<typeof vi.fn>;
    mockValidate.mockResolvedValue({ valid: true, balance_cents: 5000 });

    render(<OnboardingPage />);
    // Navigate to step 4 (validation success)
    fireEvent.click(screen.getByText("Get Started"));
    fireEvent.click(screen.getByText("Continue"));

    fireEvent.change(screen.getByLabelText("Key ID"), {
      target: { value: "key" },
    });
    fireEvent.change(screen.getByLabelText("Private Key (PEM)"), {
      target: { value: "pem" },
    });
    fireEvent.click(screen.getByText("Validate"));

    await waitFor(() => {
      expect(screen.getByText("Connected Successfully!")).toBeInTheDocument();
    });

    // Step 4 → 5 (Risk Disclaimer)
    fireEvent.click(screen.getByText("Continue"));
    expect(screen.getByText("Risk Disclaimer")).toBeInTheDocument();
    expect(screen.getByText("I Understand")).toBeInTheDocument();
  });
});
