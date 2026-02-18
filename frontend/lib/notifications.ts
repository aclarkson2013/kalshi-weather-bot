/**
 * Web Push notification helpers.
 *
 * Uses the browser Push API to subscribe the user for trade alerts
 * and settlement notifications, then sends the subscription to the backend.
 */

import { subscribePush } from "./api";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || "";

/**
 * Convert a URL-safe base64 string to a Uint8Array for applicationServerKey.
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Request notification permission and subscribe to push notifications.
 *
 * 1. Requests notification permission from the browser
 * 2. Gets or creates a PushSubscription via the service worker
 * 3. Sends the subscription to the backend for storage
 *
 * Returns true if subscription succeeded, false otherwise.
 */
export async function registerPushSubscription(): Promise<boolean> {
  try {
    // Check support
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      console.warn("Push notifications not supported");
      return false;
    }

    // Request permission
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      console.warn("Notification permission denied");
      return false;
    }

    // Get service worker registration
    const registration = await navigator.serviceWorker.ready;

    // Subscribe to push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });

    // Send to backend
    const subJson = subscription.toJSON();
    await subscribePush({
      endpoint: subJson.endpoint!,
      expirationTime: subJson.expirationTime ?? null,
      keys: subJson.keys as Record<string, string>,
    });

    return true;
  } catch (error) {
    console.error("Push subscription failed:", error);
    return false;
  }
}

/**
 * Check if push notifications are currently enabled.
 */
export async function isPushEnabled(): Promise<boolean> {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return false;
    }

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return subscription !== null;
  } catch {
    return false;
  }
}
