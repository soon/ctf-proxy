import { useState, useEffect } from "react";
import { client } from "@/client/client.gen";

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

	const storedUrl = localStorage.getItem("ctf-proxy-api-url");
	const apiUrl = storedUrl || "http://localhost:48955";

	useEffect(() => {
		const checkHealth = async () => {
			setIsChecking(true);
			setError(null);

			try {
				const response = await fetch(`${apiUrl}/api/health`);
				if (response.ok) {
					setIsHealthy(true);
					if (storedUrl && client.getConfig().baseUrl !== apiUrl) {
						client.setConfig({ baseUrl: apiUrl });
					}
				} else {
					setIsHealthy(false);
					setError(`Server responded with status ${response.status}`);
				}
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
	localStorage.setItem("ctf-proxy-api-url", url);
	client.setConfig({ baseUrl: url });
	window.location.reload();
}
