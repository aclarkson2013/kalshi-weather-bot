"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Key,
  Loader2,
  Settings,
  Shield,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { validateCredentials } from "@/lib/api";

const STEPS = [
  "Welcome",
  "Instructions",
  "API Keys",
  "Validation",
  "Risk Disclaimer",
  "Settings",
] as const;

type Step = (typeof STEPS)[number];

export default function OnboardingPage() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const [keyId, setKeyId] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [balanceCents, setBalanceCents] = useState<number | null>(null);

  const currentStep = STEPS[stepIndex];

  const goNext = () => setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  const goBack = () => setStepIndex((i) => Math.max(i - 1, 0));

  const handleValidate = async () => {
    setValidating(true);
    setValidationError(null);

    try {
      const result = await validateCredentials({
        key_id: keyId.trim(),
        private_key: privateKey.trim(),
      });
      setBalanceCents(result.balance_cents);
      goNext();
    } catch (error) {
      setValidationError(
        error instanceof Error ? error.message : "Validation failed"
      );
    } finally {
      setValidating(false);
    }
  };

  const handleFinish = () => {
    router.push("/");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-8 -mt-4">
      {/* Progress dots */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((_, i) => (
          <div
            key={i}
            className={`w-2.5 h-2.5 rounded-full transition-colors ${
              i <= stepIndex ? "bg-boz-primary" : "bg-gray-300"
            }`}
          />
        ))}
      </div>

      {/* Step content */}
      <div className="w-full max-w-md">
        {/* Step 1: Welcome */}
        {currentStep === "Welcome" && (
          <div className="text-center">
            <Sparkles size={56} className="text-boz-primary mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">
              Welcome to Boz Weather Trader
            </h1>
            <p className="text-boz-neutral mb-8">
              An automated weather prediction market trading bot for Kalshi.
              Let&apos;s get you set up.
            </p>
            <button
              onClick={goNext}
              className="min-h-[44px] w-full px-6 py-3 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
            >
              Get Started <ArrowRight size={16} />
            </button>
          </div>
        )}

        {/* Step 2: Instructions */}
        {currentStep === "Instructions" && (
          <div>
            <Key size={40} className="text-boz-primary mb-4" />
            <h2 className="text-xl font-bold mb-2">Connect to Kalshi</h2>
            <p className="text-boz-neutral mb-4">
              You&apos;ll need your Kalshi API credentials to connect.
            </p>
            <ol className="space-y-3 text-sm mb-6">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-boz-primary text-xs flex items-center justify-center font-medium">
                  1
                </span>
                <span>Log in to your Kalshi account at kalshi.com</span>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-boz-primary text-xs flex items-center justify-center font-medium">
                  2
                </span>
                <span>Navigate to Settings &rarr; API Keys</span>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-boz-primary text-xs flex items-center justify-center font-medium">
                  3
                </span>
                <span>Create a new API key pair and download the private key</span>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-boz-primary text-xs flex items-center justify-center font-medium">
                  4
                </span>
                <span>Copy the Key ID and paste the private key contents below</span>
              </li>
            </ol>
            <div className="flex gap-2">
              <button
                onClick={goBack}
                className="min-h-[44px] px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                onClick={goNext}
                className="min-h-[44px] flex-1 px-6 py-2 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
              >
                Continue <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: API Keys Input */}
        {currentStep === "API Keys" && (
          <div>
            <h2 className="text-xl font-bold mb-4">Enter API Credentials</h2>
            <div className="space-y-4 mb-6">
              <div>
                <label
                  htmlFor="keyId"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Key ID
                </label>
                <input
                  id="keyId"
                  type="text"
                  value={keyId}
                  onChange={(e) => setKeyId(e.target.value)}
                  placeholder="e.g., abc123-def456-..."
                  className="w-full min-h-[44px] px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-boz-primary focus:border-transparent outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="privateKey"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Private Key (PEM)
                </label>
                <textarea
                  id="privateKey"
                  value={privateKey}
                  onChange={(e) => setPrivateKey(e.target.value)}
                  placeholder="-----BEGIN EC PRIVATE KEY-----&#10;..."
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-boz-primary focus:border-transparent outline-none resize-none"
                />
              </div>
            </div>

            {validationError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-boz-danger flex items-center gap-2">
                <AlertTriangle size={16} />
                {validationError}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={goBack}
                className="min-h-[44px] px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                onClick={handleValidate}
                disabled={!keyId.trim() || !privateKey.trim() || validating}
                className="min-h-[44px] flex-1 px-6 py-2 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {validating ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Validating...
                  </>
                ) : (
                  <>
                    Validate <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Validation Success */}
        {currentStep === "Validation" && (
          <div className="text-center">
            <CheckCircle size={56} className="text-boz-success mx-auto mb-4" />
            <h2 className="text-xl font-bold mb-2">Connected Successfully!</h2>
            <p className="text-boz-neutral mb-2">
              Your Kalshi account is now connected.
            </p>
            {balanceCents !== null && (
              <p className="text-lg font-semibold text-boz-primary mb-8">
                Account Balance: ${(balanceCents / 100).toFixed(2)}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={goBack}
                className="min-h-[44px] px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                onClick={goNext}
                className="min-h-[44px] flex-1 px-6 py-3 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
              >
                Continue <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Risk Disclaimer */}
        {currentStep === "Risk Disclaimer" && (
          <div>
            <Shield size={40} className="text-boz-warning mb-4" />
            <h2 className="text-xl font-bold mb-2">Risk Disclaimer</h2>
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6 text-sm space-y-2">
              <p>
                <strong>Trading involves risk.</strong> Prediction markets can
                result in total loss of invested capital.
              </p>
              <p>
                Boz Weather Trader is an open-source tool provided as-is. Past
                performance does not guarantee future results.
              </p>
              <p>
                You are solely responsible for all trades made through this
                platform, whether in auto or manual mode.
              </p>
              <p>
                Start with small trade sizes and use the risk limit settings to
                protect your account.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={goBack}
                className="min-h-[44px] px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                onClick={goNext}
                className="min-h-[44px] flex-1 px-6 py-3 bg-boz-primary text-white rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
              >
                I Understand <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 6: Initial Settings */}
        {currentStep === "Settings" && (
          <div>
            <Settings size={40} className="text-boz-primary mb-4" />
            <h2 className="text-xl font-bold mb-2">You&apos;re All Set!</h2>
            <p className="text-boz-neutral mb-4">
              Your account is configured with conservative defaults:
            </p>
            <div className="bg-gray-50 rounded-lg p-4 mb-6 text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-boz-neutral">Trading Mode</span>
                <span className="font-medium">Manual</span>
              </div>
              <div className="flex justify-between">
                <span className="text-boz-neutral">Max Trade Size</span>
                <span className="font-medium">$1.00</span>
              </div>
              <div className="flex justify-between">
                <span className="text-boz-neutral">Daily Loss Limit</span>
                <span className="font-medium">$10.00</span>
              </div>
              <div className="flex justify-between">
                <span className="text-boz-neutral">Active Cities</span>
                <span className="font-medium">NYC, CHI, MIA, AUS</span>
              </div>
            </div>
            <p className="text-xs text-boz-neutral mb-6">
              You can change all settings anytime from the Settings page.
            </p>
            <button
              onClick={handleFinish}
              className="min-h-[44px] w-full px-6 py-3 bg-boz-success text-white rounded-lg font-medium hover:bg-green-700 transition-colors flex items-center justify-center gap-2"
            >
              <CheckCircle size={16} />
              Go to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
