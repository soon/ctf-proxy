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
	const [apiUrl, setApiUrl] = useState(() => {
		return (
			localStorage.getItem("ctf-proxy-api-host") || "http://localhost:48955"
		);
	});

	useEffect(() => {
		const checkHealth = async () => {
			setIsChecking(true);
			setError(null);

			try {
				const storedUrl = localStorage.getItem("ctf-proxy-api-host");
				const storedToken = localStorage.getItem("apiToken");
				const currentApiUrl = storedUrl || "http://localhost:48955";

				setApiUrl(currentApiUrl);

				const config: any = { baseUrl: currentApiUrl };
				if (storedToken) {
					config.headers = {
						...client.getConfig().headers,
						Authorization: `Bearer ${storedToken}`,
					};
				}
				client.setConfig(config);

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
	}, []);

	return { isHealthy, isChecking, error, apiUrl };
}

export function updateApiUrl(url: string) {
	localStorage.setItem("ctf-proxy-api-host", url);
	const storedToken = localStorage.getItem("apiToken");
	const config: any = { baseUrl: url };
	if (storedToken) {
		config.headers = {
			...client.getConfig().headers,
			Authorization: `Bearer ${storedToken}`,
		};
	}
	client.setConfig(config);
	window.location.reload();
}
