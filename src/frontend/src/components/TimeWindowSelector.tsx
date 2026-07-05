import { Select } from "antd";
import { ClockCircleOutlined } from "@ant-design/icons";

export interface TimeWindowSelectorProps {
	value: number;
	onChange: (value: number) => void;
	style?: React.CSSProperties;
}

const windowOptions = [
	{ value: 5, label: "Last 5 minutes" },
	{ value: 15, label: "Last 15 minutes" },
	{ value: 30, label: "Last 30 minutes" },
	{ value: 60, label: "Last hour" },
	{ value: 120, label: "Last 2 hours" },
	{ value: 360, label: "Last 6 hours" },
	{ value: 720, label: "Last 12 hours" },
	{ value: 1440, label: "Last 24 hours" },
];

export function TimeWindowSelector({
	value,
	onChange,
	style = { width: 200 },
}: TimeWindowSelectorProps) {
	return (
		<Select
			value={value}
			onChange={onChange}
			options={windowOptions}
			style={style}
			suffixIcon={<ClockCircleOutlined />}
		/>
	);
}
