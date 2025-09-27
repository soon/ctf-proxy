import { useState, useEffect } from "react";
import { client } from "@/client/client.gen";
import { healthCheckApiHealthGet } from "@/client/sdk.gen";

interface HealthCheckResult {
	isHealthy: boolean;
	isChecking: boolean;
	error: string | null;
	apiUrl: string;
}

export function useHealthCheck(): HealthCheckResult {
	const [isHealthy, setIsHealthy] = useState(false);
	const [isChecking, setIsChecking] = useState(true);
	const [error, setError] = useState<string | null>(null);

	const storedUrl = localStorage.getItem("ctf-proxy-api-host");
	const apiUrl = storedUrl || "http://localhost:48955";

	useEffect(() => {
		const checkHealth = async () => {
			setIsChecking(true);
			setError(null);

			try {
				if (storedUrl && client.getConfig().baseUrl !== apiUrl) {
					client.setConfig({ baseUrl: apiUrl });
				}

				const { data } = await healthCheckApiHealthGet();
				setIsHealthy(true);
			} catch (err) {
				setIsHealthy(false);
				setError(
					err instanceof Error ? err.message : "Failed to connect to server",
				);
			} finally {
				setIsChecking(false);
			}
		};

		checkHealth();
	}, [apiUrl, storedUrl]);

	return { isHealthy, isChecking, error, apiUrl };
}

export function updateApiUrl(url: string) {
	localStorage.setItem("ctf-proxy-api-host", url);
	client.setConfig({ baseUrl: url });
	window.location.reload();
}
