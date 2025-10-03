import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Empty, Spin, Select } from "antd";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { getCodeServerInfoApiCodeServerInfoGetOptions } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";

export const Route = createFileRoute("/code-editor")({
	staticData: {
		breadcrumb: "Code Editor",
	},
	component: CodeEditorPage,
});

function CodeEditorPage() {
	const [selectedService, setSelectedService] = useState<string | null>(null);
	const [pageActionsEl, setPageActionsEl] = useState<HTMLElement | null>(null);
	const apiToken = localStorage.getItem("apiToken") || "";

	const { data, isLoading } = useQuery({
		...getCodeServerInfoApiCodeServerInfoGetOptions(),
	});

	useEffect(() => {
		const el = document.getElementById("page-actions");
		setPageActionsEl(el);
	}, []);

	if (isLoading) {
		return (
			<div style={{ textAlign: "center", padding: "50px" }}>
				<Spin size="large" />
			</div>
		);
	}

	if (!data?.enabled || data.services.length === 0) {
		return (
			<Empty
				description={
					<span>
						No services with mount folders configured.
						<br />
						Add mount_folder to services in config to enable code editing.
					</span>
				}
			/>
		);
	}

	const currentService =
		selectedService || data.services[0]?.workspace_path || null;

	const getCodeServerUrl = (workspace: string) => {
		const baseUrl =
			client.getConfig().baseUrl || "http://ubuntu-24-04-vm.local:48955";
		return `${baseUrl}/code-server/?folder=${workspace}&tkn=${apiToken}`;
	};

	return (
		<>
			{pageActionsEl &&
				createPortal(
					<Select
						style={{ width: 250 }}
						placeholder="Select service"
						value={currentService}
						onChange={(value) => setSelectedService(value)}
						options={data.services.map((s) => ({
							label: s.name,
							value: s.workspace_path,
						}))}
					/>,
					pageActionsEl,
				)}
			{currentService && (
				<div style={{ width: "100%", height: "100%", border: "none" }}>
					<iframe
						src={getCodeServerUrl(currentService)}
						style={{
							width: "100%",
							height: "calc(100vh - 120px)",
							border: "none",
						}}
						title="Code Editor"
					/>
				</div>
			)}
		</>
	);
}
