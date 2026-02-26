import { useQueryClient } from "@tanstack/react-query";
import { useOGFields } from "../hooks/useOGFields";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import OGFieldsList from "./OGFieldsList";
import { ogfieldKeys } from "../queries/ogfields";

export default function OGFieldsView({ className, endpoint }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useOGFields();

  const handleClear = () => {
    queryClient.setQueryData(ogfieldKeys.lists(), []);
  };

  return (
    <div className={`max-w-4xl mx-auto ${className}`}>
      <h1 className="text-3xl font-bold mb-3 text-gray-800">OGFields</h1>
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
      <OGFieldsList
        ogfields={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
      />
    </div>
  );
}
