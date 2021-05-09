import { act, renderHook } from "@testing-library/react-hooks";
import { Empty } from "google-protobuf/google/protobuf/empty_pb";

import { service } from "../../service";
import * as client from "../../service/client";
import wrapper from "../../test/hookWrapper";
import { addDefaultUser } from "../../test/utils";
import { useAuthContext } from "./AuthProvider";

const logoutMock = service.user.logout as jest.Mock;
logoutMock.mockResolvedValue(new Empty());

const jailMock = service.jail.getIsJailed as jest.Mock;
jailMock.mockResolvedValue({ isJailed: true });

describe("AuthProvider", () => {
  it("sets an unauthenticatedErrorHandler function that logs out correctly", async () => {
    addDefaultUser();

    //mock out setUnauthenticatedErrorHandler to set our own handler var
    const initialHandler = async () => {};
    let handler: (e: Error) => Promise<void> = initialHandler;
    const mockSetHandler = jest.fn((fn: (e: Error) => Promise<void>) => {
      handler = fn;
    });
    jest
      .spyOn(client, "setUnauthenticatedErrorHandler")
      .mockImplementation(mockSetHandler);

    const { result } = renderHook(() => useAuthContext(), {
      wrapper,
    });

    expect(mockSetHandler).toBeCalled();
    await act(async () => {
      await handler({ message: "Unauthorized" } as Error);
    });
    expect(result.current.authState.authenticated).toBe(false);
    expect(result.current.authState.error).toBe("You were logged out.");
  });

  it("sets an unauthenticatedErrorHandler function that redirects to jail if jailed correctly", async () => {
    addDefaultUser();

    //mock out setUnauthenticatedErrorHandler to set our own handler var
    const initialHandler = async () => {};
    let handler: (e: Error) => Promise<void> = initialHandler;
    const mockSetHandler = jest.fn((fn: (e: Error) => Promise<void>) => {
      handler = fn;
    });
    jest
      .spyOn(client, "setUnauthenticatedErrorHandler")
      .mockImplementation(mockSetHandler);

    const { result } = renderHook(() => useAuthContext(), {
      wrapper,
    });

    expect(mockSetHandler).toBeCalled();
    await act(async () => {
      await handler({ message: "Permission denied" } as Error);
    });
    expect(result.current.authState.authenticated).toBe(true);
    expect(result.current.authState.jailed).toBe(true);
  });
});
