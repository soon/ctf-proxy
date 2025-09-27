import { getServicesApiServicesGetOptions } from "@/client/@tanstack/react-query.gen";
import { ServiceInfo } from "@/components/ServiceInfo";
import type { ServiceListItem } from "@/client";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
	Col,
	Input,
	Row,
	Spin,
	Typography,
	Space,
	Button,
	Card,
	Checkbox,
} from "antd";
import { useState, useEffect, useCallback, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import {
	ReloadOutlined,
	SearchOutlined,
	AlertOutlined,
} from "@ant-design/icons";

const { Text, Title } = Typography;
const { Search } = Input;

export const Route = createFileRoute("/")({
	component: Dashboard,
});

function Dashboard() {
	const navigate = useNavigate();
	const [previousData, setPreviousData] = useState<ServiceListItem[]>([]);
	const [searchTerm, setSearchTerm] = useState("");
	const [autoRefresh, setAutoRefresh] = useState(true);
	const refreshInterval = 5000;
	const [actionsContainer, setActionsContainer] = useState<HTMLElement | null>(
		null,
	);

	const { data, isLoading, error, refetch } = useQuery({
		...getServicesApiServicesGetOptions(),
		refetchInterval: autoRefresh ? refreshInterval : false,
	});

	useEffect(() => {
		if (data?.services) {
			setPreviousData((current) => {
				if (current.length === 0) return data.services;
				return current;
			});

			const timer = setTimeout(() => {
				setPreviousData(data.services);
			}, 1000);

			return () => clearTimeout(timer);
		}
	}, [data?.services]);

	const handleSearch = useCallback(
		(value: string) => {
			const trimmed = value.trim();

			if (trimmed.startsWith("s ") || trimmed.startsWith("/s ")) {
				const port = trimmed.replace(/^\/?s\s+/, "");
				if (port && !isNaN(Number(port))) {
					navigate({ to: `/service/${port}` });
				}
			} else if (trimmed.startsWith("r ") || trimmed.startsWith("/r ")) {
				const reqId = trimmed.replace(/^\/?r\s+/, "");
				if (reqId && !isNaN(Number(reqId))) {
					// Request routes now need port, just use a placeholder
					navigate({ to: `/service/3000/request/${reqId}` });
				}
			} else if (trimmed.startsWith("p ") || trimmed.startsWith("/p ")) {
				const port = trimmed.replace(/^\/?p\s+/, "");
				if (port && !isNaN(Number(port))) {
					navigate({ to: `/service/${port}/paths` });
				}
			} else if (trimmed === "h" || trimmed === "/h" || trimmed === "help") {
				alert(`Commands:
s <port> - Open service detail
r <req_id> - Open request detail
p <port> - Open path stats
h - Show help`);
			} else {
				setSearchTerm(trimmed);
			}
		},
		[navigate],
	);

	const handleServiceClick = (port: number) => {
		navigate({ to: `/service/${port}` });
	};

	const filteredServices = data?.services?.filter((service) => {
		if (!searchTerm) return true;
		const search = searchTerm.toLowerCase();
		return (
			service.name.toLowerCase().includes(search) ||
			service.port.toString().includes(search) ||
			service.type.toLowerCase().includes(search)
		);
	});

	useLayoutEffect(() => {
		const container = document.getElementById("page-actions");
		setActionsContainer(container);
	}, []);

	if (error) {
		return (
			<div className="flex items-center justify-center h-screen">
				<Card className="w-96">
					<div className="text-center">
						<AlertOutlined className="text-4xl text-red-500 mb-4" />
						<Title level={4}>Failed to load services</Title>
						<Text type="secondary">{error.message}</Text>
						<div className="mt-4">
							<Button type="primary" onClick={() => refetch()}>
								Retry
							</Button>
						</div>
					</div>
				</Card>
			</div>
		);
	}

	return (
		<>
			{actionsContainer &&
				createPortal(
					<Space>
						<Checkbox
							checked={autoRefresh}
							onChange={(e) => setAutoRefresh(e.target.checked)}
						>
							Auto-refresh ({refreshInterval / 1000}s)
						</Checkbox>
						<Button
							onClick={() => refetch()}
							icon={isLoading ? <ReloadOutlined spin /> : <ReloadOutlined />}
							size="small"
							disabled={isLoading}
						>
							{isLoading ? "Refreshing" : "Refresh"}
						</Button>
					</Space>,
					actionsContainer,
				)}

			{/* Search */}
			<Search
				placeholder="Search or command (s <port>, r <req_id>, h for help)"
				allowClear
				enterButton={<SearchOutlined />}
				size="middle"
				onSearch={handleSearch}
				onChange={(e) => setSearchTerm(e.target.value)}
				className="mb-4"
			/>

			{/* Services Grid */}
			{isLoading && filteredServices === undefined ? (
				<div className="flex justify-center items-center h-64">
					<Spin size="large" tip="Loading services..." />
				</div>
			) : (
				<Row gutter={[8, 8]}>
					{filteredServices?.map((service) => {
						const prevService = previousData.find(
							(p) => p.port === service.port,
						);
						return (
							<Col
								key={service.port}
								xs={24}
								sm={12}
								md={12}
								lg={8}
								xl={6}
								xxl={4}
							>
								<ServiceInfo
									service={service}
									previousService={prevService}
									onClick={handleServiceClick}
								/>
							</Col>
						);
					})}
					{filteredServices?.length === 0 && (
						<Col span={24}>
							<Card className="text-center">
								<Text type="secondary">No services found</Text>
							</Card>
						</Col>
					)}
				</Row>
			)}

			{/* Last Update */}
			{data?.timestamp && (
				<div className="text-center mt-2">
					<Text type="secondary" className="text-xs">
						Last: {new Date(data.timestamp).toLocaleTimeString()}
					</Text>
				</div>
			)}
		</>
	);
}
