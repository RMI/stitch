import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useResource } from "../hooks/useResources";
import FetchButton from "./FetchButton";
import ClearCacheButton from "./ClearCacheButton";
import JsonView from "./JsonView";
import Input from "./Input";
import { resourceKeys } from "../queries/resources";

export default function ResourceView({ className, endpoint }) {
  const queryClient = useQueryClient();
  const [id, setId] = useState(1);
  const { data, isLoading, isError, error, refetch } = useResource(id);

  const handleClear = (id) => {
    queryClient.resetQueries({ queryKey: resourceKeys.detail(id) });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      refetch();
    }
  };

  return (
    <div className={`max-w-4xl mx-auto ${className}`}>
      <h1 className="text-3xl font-bold mb-3 text-gray-800">Resource {id}</h1>
      <div className=" text-gray-500 pb-4">
        <span className="font-bold">
          {import.meta.env.VITE_API_URL}
          {endpoint}
        </span>
      </div>
      <div className="mb-6 flex gap-3">
        <Input
          type="number"
          value={id}
          onChange={(e) => setId(Number(e.target.value))}
          onKeyDown={handleKeyDown}
          min={1}
          max={1000}
          className="w-24"
        />
        <FetchButton onFetch={() => refetch()} isLoading={isLoading} />
        <ClearCacheButton
          onClear={() => handleClear(id)}
          disabled={!data && !error}
        />
      </div>
      <JsonView
        data={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        message={`No resource loaded. Click the button above to fetch a resource.`}
      />
    </div>
  );
}
