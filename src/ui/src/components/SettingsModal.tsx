import { useState, useEffect } from "react";
import { Modal, Input, Button, message, App } from "antd";
import { updateApiUrl } from "@/hooks/useHealthCheck";

interface SettingsModalProps {
	open: boolean;
	onClose: () => void;
}

const STORAGE_KEY = "ctf-proxy-api-host";
const DEFAULT_API_HOST = "http://localhost:48955";

export default function SettingsModal({ open, onClose }: SettingsModalProps) {
	const [apiHost, setApiHost] = useState(() => {
		return localStorage.getItem(STORAGE_KEY) || DEFAULT_API_HOST;
	});

	useEffect(() => {
		const savedHost = localStorage.getItem(STORAGE_KEY);
		if (savedHost) {
			setApiHost(savedHost);
		}
	}, [open]);

	const validateUrl = (url: string): boolean => {
		// Basic validation - must start with http:// or https://
		if (!url.startsWith("http://") && !url.startsWith("https://")) {
			return false;
		}

		try {
			// Try to parse as URL - this handles IPv4, IPv6, and hostnames
			// IPv6 URLs should be in format: http://[::1]:8080 or http://[2001:db8::1]:8080
			new URL(url);
			return true;
		} catch {
			return false;
		}
	};

	const handleSave = () => {
		let cleanedHost = apiHost.trim();

		// Remove trailing slashes
		while (cleanedHost.endsWith("/")) {
			cleanedHost = cleanedHost.slice(0, -1);
		}

		if (!validateUrl(cleanedHost)) {
			message.error(
				"Invalid URL format. Please enter a valid URL (e.g., http://localhost:48955 or http://[::1]:48955 for IPv6)",
				10,
			);
			return;
		}

		message.success("API host updated successfully. Refreshing page...", 2);
		// Use the same updateApiUrl function as HostConfig
		updateApiUrl(cleanedHost);
	};

	const handleReset = () => {
		setApiHost(DEFAULT_API_HOST);
		localStorage.removeItem(STORAGE_KEY);
		message.success("API host reset to default. Refreshing page...", 2);
		// Use the same updateApiUrl function as HostConfig
		updateApiUrl(DEFAULT_API_HOST);
	};

	return (
		<Modal
			title="Settings"
			open={open}
			onCancel={onClose}
			footer={[
				<Button key="reset" onClick={handleReset}>
					Reset to Default
				</Button>,
				<Button key="cancel" onClick={onClose}>
					Cancel
				</Button>,
				<Button key="save" type="primary" onClick={handleSave}>
					Save
				</Button>,
			]}
		>
			<div className="py-4">
				<label className="block mb-2 font-medium">API Host</label>
				<Input
					value={apiHost}
					onChange={(e) => setApiHost(e.target.value)}
					placeholder="http://localhost:48955"
				/>
				<p className="mt-2 text-sm text-gray-500">
					Enter the URL of the API server:
					<br />• IPv4: http://localhost:48955 or http://192.168.1.1:48955
					<br />• IPv6: http://[::1]:48955 or http://[2001:db8::1]:48955
				</p>
			</div>
		</Modal>
	);
}
