import { useQueryClient } from "@tanstack/react-query";
import { useResources } from "../hooks/useResources";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import ResourcesList from "./ResourcesList";
import { resourceKeys } from "../queries/resources";

export default function ResourcesView({ className, endpoint }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useResources();

  const handleClear = () => {
    queryClient.setQueryData(resourceKeys.lists(), []);
  };

  return (
    <div className={`max-w-4xl mx-auto ${className}`}>
      <h1 className="text-3xl font-bold mb-3 text-gray-800">Resources</h1>
      <div className=" text-gray-500 pb-4">
        <span className="font-bold">{endpoint}</span>
      </div>
      <div className="mb-6 flex gap-3">
        <FetchButton onFetch={() => refetch()} isLoading={isLoading} />
        <ClearCacheButton
          onClear={handleClear}
          disabled={!data?.length && !isError}
        />
      </div>
      <ResourcesList
        resources={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
      />
    </div>
  );
}
