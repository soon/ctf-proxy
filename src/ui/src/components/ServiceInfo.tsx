import type { ServiceListItem } from "@/client";
import { Badge, Card, Progress, Statistic, Tag, Typography } from "antd";
import {
	ApiOutlined,
	CheckCircleOutlined,
	CloseCircleOutlined,
	FlagOutlined,
	SwapOutlined,
	WarningOutlined,
} from "@ant-design/icons";
import { useState, useEffect } from "react";

const { Text, Title } = Typography;

export interface ServiceInfoProps {
	service: ServiceListItem;
	previousService?: ServiceListItem;
	onClick?: (port: number) => void;
}

export function ServiceInfo({
	service,
	previousService,
	onClick,
}: ServiceInfoProps) {
	const [deltas, setDeltas] = useState<Record<string, number>>({});

	useEffect(() => {
		if (previousService) {
			setDeltas({
				totalRequests:
					service.stats.total_requests - previousService.stats.total_requests,
				totalResponses:
					service.stats.total_responses - previousService.stats.total_responses,
				blockedRequests:
					service.stats.blocked_requests -
					previousService.stats.blocked_requests,
				blockedResponses:
					service.stats.blocked_responses -
					previousService.stats.blocked_responses,
				flagsWritten:
					service.stats.flags_written - previousService.stats.flags_written,
				flagsRetrieved:
					service.stats.flags_retrieved - previousService.stats.flags_retrieved,
				flagsBlocked:
					service.stats.flags_blocked - previousService.stats.flags_blocked,
			});
		}
	}, [service, previousService]);

	const getStatusColor = () => {
		if (service.stats.alerts_count > 0) return "error";
		if (service.stats.blocked_requests > 0) return "warning";
		return "success";
	};

	const formatDelta = (value: number) => {
		if (value === 0) return "";
		return value > 0 ? `+${value}` : `${value}`;
	};

	const successRate =
		service.stats.total_responses > 0
			? (service.stats.success_responses / service.stats.total_responses) * 100
			: 0;

	const topStatuses = Object.entries(service.stats.status_counts || {})
		.sort(([, a], [, b]) => b - a)
		.slice(0, 3);

	const shortName = service.name.substring(0, 4).toUpperCase();

	return (
		<Badge.Ribbon
			text={service.type}
			color={service.type === "http" ? "blue" : "green"}
		>
			<Card
				size="small"
				hoverable
				onClick={() => onClick?.(service.port)}
				title={
					<div className="flex justify-between items-center">
						<span className="font-bold text-sm">
							{shortName}:{service.port}
						</span>
						<Badge status={getStatusColor() as any} />
					</div>
				}
				className="cursor-pointer transition-all hover:shadow-lg"
				styles={{ body: { padding: "8px" } }}
			>
				<div className="space-y-1">
					{/* Flags Section */}
					<div className="bg-blue-50 p-1 rounded">
						<div className="flex items-center gap-1 mb-0.5">
							<FlagOutlined className="text-blue-600 text-xs" />
							<Text strong className="text-xs">
								Flags
							</Text>
						</div>
						<div className="flex justify-between text-xs">
							<span>
								↓{service.stats.flags_written}
								<span className="text-gray-400 ml-0.5">
									{deltas.flagsWritten ? formatDelta(deltas.flagsWritten) : ""}
								</span>
							</span>
							<span>
								↑{service.stats.flags_retrieved}
								<span className="text-gray-400 ml-0.5">
									{deltas.flagsRetrieved
										? formatDelta(deltas.flagsRetrieved)
										: ""}
								</span>
							</span>
							<span
								className={
									service.stats.flags_blocked > 0 ? "text-red-500" : ""
								}
							>
								✖{service.stats.flags_blocked}
							</span>
						</div>
					</div>

					{/* Traffic Section */}
					<div className="bg-green-50 p-1 rounded">
						<div className="flex items-center gap-1 mb-0.5">
							<SwapOutlined className="text-green-600 text-xs" />
							<Text strong className="text-xs">
								Traffic
							</Text>
						</div>
						<div className="flex justify-between text-xs">
							<span>
								→{service.stats.total_requests}
								<span className="text-gray-400 ml-0.5">
									{deltas.totalRequests
										? formatDelta(deltas.totalRequests)
										: ""}
								</span>
							</span>
							<span>
								←{service.stats.total_responses}
								<span className="text-gray-400 ml-0.5">
									{deltas.totalResponses
										? formatDelta(deltas.totalResponses)
										: ""}
								</span>
							</span>
						</div>
						{(service.stats.blocked_requests > 0 ||
							service.stats.blocked_responses > 0) && (
							<div className="flex justify-between text-xs text-red-500 mt-0.5">
								<span>✖→{service.stats.blocked_requests}</span>
								<span>✖←{service.stats.blocked_responses}</span>
							</div>
						)}
					</div>

					{/* Status Codes */}
					{topStatuses.length > 0 && (
						<div className="flex gap-0.5 flex-wrap">
							{topStatuses.map(([status, count]) => (
								<span
									key={status}
									className={`text-xs px-1 rounded ${
										status.startsWith("2")
											? "bg-green-100 text-green-700"
											: status.startsWith("4")
												? "bg-yellow-100 text-yellow-700"
												: status.startsWith("5")
													? "bg-red-100 text-red-700"
													: "bg-gray-100 text-gray-700"
									}`}
								>
									{status}:{count}
								</span>
							))}
						</div>
					)}

					{/* Success Rate */}
					<Progress
						percent={Math.round(successRate)}
						size="small"
						strokeColor={
							successRate > 90
								? "#52c41a"
								: successRate > 70
									? "#faad14"
									: "#ff4d4f"
						}
						showInfo={false}
						strokeWidth={3}
					/>

					{/* Alerts */}
					{service.stats.alerts_count > 0 && (
						<div className="bg-red-50 p-1 rounded">
							<div className="flex items-center gap-1">
								<WarningOutlined className="text-red-600 text-xs" />
								<Text strong className="text-red-600 text-xs">
									{service.stats.alerts_count} Alert
									{service.stats.alerts_count !== 1 ? "s" : ""}
								</Text>
							</div>
							{service.stats.recent_alerts &&
								service.stats.recent_alerts.length > 0 && (
									<div className="mt-0.5 text-xs space-y-0.5">
										{service.stats.recent_alerts
											.slice(0, 1)
											.map(([description], idx) => (
												<div
													key={idx}
													className="text-red-600 truncate text-xs"
												>
													{description}
												</div>
											))}
									</div>
								)}
						</div>
					)}

					{/* Stats */}
					<div className="flex justify-between text-xs text-gray-500">
						<span>P:{service.stats.unique_paths}</span>
						<span>H:{service.stats.unique_headers}</span>
						<span>{Math.round(successRate)}%</span>
					</div>
				</div>
			</Card>
		</Badge.Ribbon>
	);
}
