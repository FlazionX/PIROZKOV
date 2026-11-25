#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <exdisp.h>
#include <servprov.h>
#include <oleauto.h>
#include <vector>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "shell32.lib")

static IFolderView* g_view = nullptr;
static IFolderView2* g_view2 = nullptr;
static std::vector<LPITEMIDLIST> g_items;
static DWORD g_originalFolderFlags = 0;
static bool g_haveFolderFlags = false;
static bool g_comInitialized = false;

static void release_all()
{
    for (auto* pidl : g_items) {
        if (pidl) ILFree(pidl);
    }
    g_items.clear();

    if (g_haveFolderFlags && g_view2) {
        g_view2->SetCurrentFolderFlags(FWF_AUTOARRANGE,
            g_originalFolderFlags & FWF_AUTOARRANGE);
    }
    g_haveFolderFlags = false;

    if (g_view2) {
        g_view2->Release();
        g_view2 = nullptr;
    }
    if (g_view) {
        g_view->Release();
        g_view = nullptr;
    }
    if (g_comInitialized) {
        CoUninitialize();
        g_comInitialized = false;
    }
}

extern "C" __declspec(dllexport) int __cdecl dance_icons_init()
{
    release_all();

    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) return 0;
    g_comInitialized = true;

    IShellWindows* shellWindows = nullptr;
    hr = CoCreateInstance(CLSID_ShellWindows, nullptr, CLSCTX_ALL,
        IID_PPV_ARGS(&shellWindows));
    if (FAILED(hr) || !shellWindows) {
        release_all();
        return 0;
    }

    VARIANT desktop;
    VARIANT root;
    VariantInit(&desktop);
    VariantInit(&root);
    desktop.vt = VT_I4;
    desktop.lVal = CSIDL_DESKTOP;

    long desktopHwnd = 0;
    IDispatch* desktopDispatch = nullptr;
    hr = shellWindows->FindWindowSW(&desktop, &root, SWC_DESKTOP,
        &desktopHwnd, SWFO_NEEDDISPATCH, &desktopDispatch);
    shellWindows->Release();

    if (FAILED(hr) || !desktopDispatch) {
        release_all();
        return 0;
    }

    IServiceProvider* serviceProvider = nullptr;
    hr = desktopDispatch->QueryInterface(IID_PPV_ARGS(&serviceProvider));
    desktopDispatch->Release();
    if (FAILED(hr) || !serviceProvider) {
        release_all();
        return 0;
    }

    IShellBrowser* browser = nullptr;
    hr = serviceProvider->QueryService(SID_STopLevelBrowser,
        IID_PPV_ARGS(&browser));
    serviceProvider->Release();
    if (FAILED(hr) || !browser) {
        release_all();
        return 0;
    }

    IShellView* shellView = nullptr;
    hr = browser->QueryActiveShellView(&shellView);
    browser->Release();
    if (FAILED(hr) || !shellView) {
        release_all();
        return 0;
    }

    hr = shellView->QueryInterface(IID_PPV_ARGS(&g_view));
    shellView->Release();
    if (FAILED(hr) || !g_view) {
        release_all();
        return 0;
    }

    if (SUCCEEDED(g_view->QueryInterface(IID_PPV_ARGS(&g_view2))) && g_view2) {
        if (SUCCEEDED(g_view2->GetCurrentFolderFlags(&g_originalFolderFlags))) {
            g_haveFolderFlags = true;
            // Temporarily disable auto-arrange so Explorer does not snap every
            // animated position back into its original grid slot.
            g_view2->SetCurrentFolderFlags(FWF_AUTOARRANGE, 0);
        }
    }

    int count = 0;
    hr = g_view->ItemCount(SVGIO_ALLVIEW, &count);
    if (FAILED(hr) || count <= 0) {
        release_all();
        return 0;
    }

    g_items.reserve(static_cast<size_t>(count));
    for (int i = 0; i < count; ++i) {
        LPITEMIDLIST pidl = nullptr;
        hr = g_view->Item(i, IID_PPV_ARGS(&pidl));
        if (SUCCEEDED(hr) && pidl) {
            g_items.push_back(pidl);
        }
    }

    if (g_items.empty()) {
        release_all();
        return 0;
    }
    return static_cast<int>(g_items.size());
}

extern "C" __declspec(dllexport) int __cdecl dance_icons_get_position(
    int index, int* x, int* y)
{
    if (!g_view || !x || !y || index < 0 ||
        static_cast<size_t>(index) >= g_items.size()) return 0;

    POINT point = {};
    HRESULT hr = g_view->GetItemPosition(g_items[static_cast<size_t>(index)], &point);
    if (FAILED(hr)) return 0;
    *x = point.x;
    *y = point.y;
    return 1;
}

extern "C" __declspec(dllexport) int __cdecl dance_icons_set_positions(
    const int* xs, const int* ys, int count)
{
    if (!g_view || !xs || !ys || count <= 0 ||
        static_cast<size_t>(count) != g_items.size()) return 0;

    std::vector<POINT> points(static_cast<size_t>(count));
    for (int i = 0; i < count; ++i) {
        points[static_cast<size_t>(i)].x = xs[i];
        points[static_cast<size_t>(i)].y = ys[i];
    }

    HRESULT hr = g_view->SelectAndPositionItems(
        static_cast<UINT>(count),
        reinterpret_cast<PCUITEMID_CHILD_ARRAY>(g_items.data()),
        points.data(),
        SVSI_POSITIONITEM
    );
    return SUCCEEDED(hr) ? 1 : 0;
}

extern "C" __declspec(dllexport) void __cdecl dance_icons_shutdown()
{
    release_all();
}
